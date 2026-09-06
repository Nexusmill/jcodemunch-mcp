"""Gated finding 2026-09-05 (colibri review of tools/index_repo.py, MEDIUM):
a changed file whose GitHub fetch failed lost its symbols silently.

`fetch_with_limit` mapped any exception to "", the builder skipped empty
content, so the file was in `changed` (blob-sha diff) but absent from
`raw_files_subset`; `incremental_save(changed_files=changed)` then DELETED its
symbols and inserted nothing, and the result carried no warning. (Failed
fetches already kept their old blob sha, so the next run retried - the gap was
transient but invisible.) Idiom follows tests/test_v1_108_127.py.
"""

from unittest.mock import AsyncMock

import pytest

from jcodemunch_mcp.parser import Symbol
from jcodemunch_mcp.storage import IndexStore
from jcodemunch_mcp.tools import index_repo as index_repo_mod

OWNER, REPO = "jgravelle", "GroqApiLibrary"
A, B = "a.py", "b.py"
A_CONTENT = "def foo():\n    return 1\n"
B_CONTENT = "def bar():\n    return 2\n"
B_CONTENT_2 = "def bar2():\n    return 3\n"


def _sym(file: str, name: str, content: str) -> Symbol:
    return Symbol(
        id=f"{file}::{name}", file=file, name=name, qualified_name=name, kind="function",
        language="python", signature=f"def {name}():", summary="", byte_offset=0,
        byte_length=len(content),
    )


def _preseed(storage_path: str) -> None:
    store = IndexStore(base_path=storage_path)
    store.save_index(
        owner=OWNER, name=REPO,
        source_files=[A, B],
        symbols=[_sym(A, "foo", A_CONTENT), _sym(B, "bar", B_CONTENT)],
        raw_files={A: A_CONTENT, B: B_CONTENT},
        languages={"python": 2},
        file_blob_shas={A: "sha_a1", B: "sha_b1"},
    )


def _names(storage_path: str) -> set:
    idx = IndexStore(base_path=storage_path).load_index(OWNER, REPO)
    return {s["name"] for s in idx.symbols}


@pytest.mark.asyncio
async def test_a_failed_fetch_keeps_the_files_symbols_and_is_reported(tmp_path, monkeypatch):
    storage = str(tmp_path)
    _preseed(storage)
    assert _names(storage) == {"foo", "bar"}

    tree = [
        {"path": A, "type": "blob", "sha": "sha_a2", "size": len(A_CONTENT)},  # changed, fetch will fail
        {"path": B, "type": "blob", "sha": "sha_b2", "size": len(B_CONTENT_2)},  # changed, fetch ok
    ]
    monkeypatch.setattr(index_repo_mod, "fetch_repo_tree", AsyncMock(return_value=(tree, "tree2")))
    monkeypatch.setattr(index_repo_mod, "fetch_gitignore", AsyncMock(return_value=""))

    async def fetch(owner, repo, path, token=None):
        if path == A:
            raise RuntimeError("503 from GitHub")
        return B_CONTENT_2

    monkeypatch.setattr(index_repo_mod, "fetch_file_content", fetch)

    result = await index_repo_mod.index_repo(
        url=f"{OWNER}/{REPO}", use_ai_summaries=False, storage_path=storage, incremental=True,
    )
    assert result.get("success") is True, result
    # b.py was updated; a.py's symbols survived the failed fetch.
    assert _names(storage) == {"foo", "bar2"}, _names(storage)
    assert result.get("changed") == 1, result
    warnings = " ".join(result.get("warnings") or [])
    assert A in warnings and "fetch" in warnings.lower(), result.get("warnings")
    # The failed file keeps its OLD blob sha so the next run retries it.
    idx = IndexStore(base_path=storage).load_index(OWNER, REPO)
    assert idx.file_blob_shas[A] == "sha_a1" and idx.file_blob_shas[B] == "sha_b2"
