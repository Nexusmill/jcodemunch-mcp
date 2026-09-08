"""B2 spec item 2, proven WITHOUT git commits: `load_repo_index_or_error` follows the
checked-out branch when the index holds a delta for it.

Why commit-free: on this machine every `git commit` - including one inside a pytest
fixture repo - runs the machine-wide adversarial gate (docket EV-045, ruling pending), so
these tests build the checkout state by hand: `git init` (no commit) plus a hand-written
`.git/HEAD`, and seed the base index + branch delta through the store API. The real-git
acceptance battery lives in tests/test_branch_following.py and is owed once EV-045 is ruled.

Plan: Nexusmill docs/superpowers/plans/2026-09-07-jcm-branch-following.md, Task 5.
Fixture rule: branch bytes differ from base bytes at offset 0.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jcodemunch_mcp.retrieval.freshness import _clear_head_cache
from jcodemunch_mcp.storage import IndexStore
from jcodemunch_mcp.tools._utils import load_repo_index_or_error
from jcodemunch_mcp.tools.search_text import search_text
from tests.test_branch_content_dir import BASE_MAIN, BASE_UTILS, BRANCH_MAIN, BRANCH_NEW, _base, _delta
from tests.test_branch_no_change_head import _git, _have_git

pytestmark = pytest.mark.skipif(not _have_git(), reason="git not available")

OWNER, NAME = "local", "follow-repo"


def _checkout(tmp_path: Path, head: str) -> Path:
    """A git dir with NO commits whose HEAD file says `head` (a ref line or a bare sha)."""
    repo = tmp_path / "src"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / ".git" / "HEAD").write_text(head + "\n", encoding="utf-8")
    return repo


def _seed(tmp_path: Path, head: str = "ref: refs/heads/feature/x", with_delta: bool = True):
    repo = _checkout(tmp_path, head)
    store = IndexStore(base_path=str(tmp_path / "idx"))
    _base(store._sqlite)
    # re-save with THIS repo as source_root (the _base helper pins /tmp/test-repo)
    store._sqlite.save_index(
        owner=OWNER, name=NAME,
        source_files=["src/main.py", "src/utils.py"],
        symbols=[], raw_files={"src/main.py": BASE_MAIN, "src/utils.py": BASE_UTILS},
        file_hashes={"src/main.py": "h_main", "src/utils.py": "h_utils"},
        git_head="aaa111", source_root=str(repo),
        file_languages={"src/main.py": "python", "src/utils.py": "python"},
    )
    if with_delta:
        _delta(store._sqlite, owner=OWNER, name=NAME)  # branch "feature/x", git_head "bbb222"
    _clear_head_cache()
    return repo, store, str(tmp_path / "idx")


class TestFollowCheckout:
    def test_omitted_branch_serves_the_composed_view_of_the_checkout(self, tmp_path):
        repo, store, sp = _seed(tmp_path)
        idx, err, _ = load_repo_index_or_error(f"{OWNER}/{NAME}", sp)
        assert err is None
        assert idx.branch == "feature/x"
        assert idx.delta_files == frozenset({"src/main.py", "src/new.py"})
        assert store.get_file_content(OWNER, NAME, "src/main.py", _index=idx) == BRANCH_MAIN
        assert store.get_file_content(OWNER, NAME, "src/new.py", _index=idx) == BRANCH_NEW
        assert store.get_file_content(OWNER, NAME, "src/utils.py", _index=idx) == BASE_UTILS
        assert idx.git_head == "bbb222"  # the branch head, not the base's aaa111

    def test_a_reader_serves_branch_bytes_through_the_follow(self, tmp_path):
        repo, store, sp = _seed(tmp_path)
        hits = {r["file"] for r in search_text(f"{OWNER}/{NAME}", "XX = 1", storage_path=sp)["results"]}
        assert hits == {"src/main.py"}
        hits = {r["file"] for r in search_text(f"{OWNER}/{NAME}", "def qux", storage_path=sp)["results"]}
        assert hits == {"src/new.py"}

    def test_get_symbol_narrow_path_yields_to_the_composed_view(self, tmp_path):
        # found by the EV-045 acceptance run: get_symbol's selective view reads BASE rows only,
        # so a delta symbol was "not found" on a branch checkout; on a checkout with a delta
        # the narrow path must yield to load_view
        from jcodemunch_mcp.tools.get_symbol import get_symbol_source
        repo, store, sp = _seed(tmp_path)
        res = get_symbol_source(f"{OWNER}/{NAME}", symbol_id="src/new.py:qux", storage_path=sp)
        assert res.get("source") == BRANCH_NEW, res
        (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        res = get_symbol_source(f"{OWNER}/{NAME}", symbol_id="src/new.py:qux", storage_path=sp)
        assert "error" in res and "not found" in res["error"].lower(), res   # base view again

    def test_explicit_branch_is_authoritative(self, tmp_path):
        repo, store, sp = _seed(tmp_path)
        idx, err, _ = load_repo_index_or_error(f"{OWNER}/{NAME}", sp, branch="main")
        assert err is None
        assert idx.delta_files == frozenset()
        assert store.get_file_content(OWNER, NAME, "src/main.py", _index=idx) == BASE_MAIN

    def test_detached_head_falls_back_to_base(self, tmp_path):
        repo, store, sp = _seed(tmp_path, head="b" * 40)
        idx, err, _ = load_repo_index_or_error(f"{OWNER}/{NAME}", sp)
        assert err is None and idx.delta_files == frozenset()
        assert store.get_file_content(OWNER, NAME, "src/main.py", _index=idx) == BASE_MAIN

    def test_checkout_without_a_delta_stays_on_base(self, tmp_path):
        repo, store, sp = _seed(tmp_path, head="ref: refs/heads/other")
        idx, err, _ = load_repo_index_or_error(f"{OWNER}/{NAME}", sp)
        assert err is None and idx.delta_files == frozenset() and idx.branch != "other"

    def test_non_git_source_root_stays_on_base(self, tmp_path):
        repo, store, sp = _seed(tmp_path)
        import shutil
        shutil.rmtree(repo / ".git")
        _clear_head_cache()
        idx, err, _ = load_repo_index_or_error(f"{OWNER}/{NAME}", sp)
        assert err is None and idx.delta_files == frozenset()

    def test_switching_base_branch_base_leaks_neither_view(self, tmp_path):
        repo, store, sp = _seed(tmp_path)
        on_branch, _, _ = load_repo_index_or_error(f"{OWNER}/{NAME}", sp)
        assert on_branch.branch == "feature/x"
        (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        on_main, _, _ = load_repo_index_or_error(f"{OWNER}/{NAME}", sp)
        assert on_main.delta_files == frozenset()
        assert store.get_file_content(OWNER, NAME, "src/main.py", _index=on_main) == BASE_MAIN
        (repo / ".git" / "HEAD").write_text("ref: refs/heads/feature/x\n", encoding="utf-8")
        again, _, _ = load_repo_index_or_error(f"{OWNER}/{NAME}", sp)
        assert again.branch == "feature/x"
        assert store.get_file_content(OWNER, NAME, "src/main.py", _index=again) == BRANCH_MAIN
        assert on_main.delta_files == frozenset() and on_main.branch != "feature/x"
        assert not (store._content_dir(OWNER, NAME) / "src/new.py").exists()

    # -- gate round 1 on B2 part 2 (gate_20260907-182123): three findings, all confirmed --

    def test_content_cache_reads_the_view_it_is_given(self, tmp_path):
        # finding 1: internal content reads that omit `_index` fall back to BASE bytes on a
        # followed checkout (the call-graph memo, dead-code scans, blast radius, references)
        from jcodemunch_mcp.tools._call_graph import _ContentCache
        repo, store, sp = _seed(tmp_path)
        idx, err, _ = load_repo_index_or_error(f"{OWNER}/{NAME}", sp)
        assert err is None and idx.branch == "feature/x"
        cache = _ContentCache(store, OWNER, NAME, index=idx)
        assert cache.content("src/main.py") == BRANCH_MAIN
        assert cache.content("src/new.py") == BRANCH_NEW

    def test_find_references_cache_does_not_cross_views(self, tmp_path):
        # finding 3: result caches keyed on owner/name only served feature-branch results
        # after `git checkout main` (a checkout switch writes nothing, so nothing invalidates)
        from jcodemunch_mcp.tools.find_references import find_references
        repo, store, sp = _seed(tmp_path)
        first = find_references(f"{OWNER}/{NAME}", "foo", storage_path=sp)
        assert "error" not in first, first
        (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        second = find_references(f"{OWNER}/{NAME}", "foo", storage_path=sp)
        assert not second["_meta"].get("cache_hit"), second["_meta"]

    def test_blast_radius_cache_does_not_cross_views(self, tmp_path):
        from jcodemunch_mcp.tools.get_blast_radius import get_blast_radius
        repo, store, sp = _seed(tmp_path)
        first = get_blast_radius(f"{OWNER}/{NAME}", "foo", storage_path=sp)
        assert "error" not in first, first
        (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        second = get_blast_radius(f"{OWNER}/{NAME}", "foo", storage_path=sp)
        # the base view seeds no symbols, so the honest answer here is an error - never the
        # cached branch result
        assert second.get("_meta", {}).get("cache_hit") is not True, second

    def test_summarize_repo_never_writes_branch_symbols_into_the_base(self, tmp_path, monkeypatch):
        # gate round 4: summarize_repo is a WRITER (incremental_save of the summarised symbols into
        # the base index); reading the composed view would persist branch-only symbols into base
        import jcodemunch_mcp.tools.summarize_repo as sr
        monkeypatch.setattr(sr, "summarize_symbols", lambda symbols, **kw: symbols)  # no AI call
        repo, store, sp = _seed(tmp_path)
        assert store.load_index(OWNER, NAME).symbols == []          # the base holds no symbols
        res = sr.summarize_repo(f"{OWNER}/{NAME}", storage_path=sp)
        assert "error" not in res, res
        base_ids = {s["id"] for s in store.load_index(OWNER, NAME).symbols}
        assert "src/new.py:qux" not in base_ids and "src/main.py:foo" not in base_ids, base_ids

    def test_following_never_spawns_git(self, tmp_path, monkeypatch):
        repo, store, sp = _seed(tmp_path)
        load_repo_index_or_error(f"{OWNER}/{NAME}", sp)  # warm caches

        def boom(*a, **k):
            raise AssertionError("subprocess spawned on the retrieval path")

        monkeypatch.setattr(subprocess, "run", boom)
        monkeypatch.setattr(subprocess, "Popen", boom)
        idx, err, _ = load_repo_index_or_error(f"{OWNER}/{NAME}", sp)
        assert err is None and idx.branch == "feature/x"


# Writers load the BASE on purpose (they decide base-vs-delta themselves); every other
# tool must take the checkout-following view. Enforced structurally: a tool that calls
# store.load_index directly serves base bytes on a branch checkout (the B2 gap found
# 2026-09-07: search_text bypassed the shared loader and scanned the base view).
LOAD_INDEX_ALLOWED = {
    "index_folder.py", "index_file.py", "index_repo.py", "index_dependency.py",
    "embed_repo.py", "_utils.py",
    # reindex-decision paths: they compare the BASE index's generation / validate the
    # repo before a reindex, so the base is the right view for them
    "refresh.py", "register_edit.py",
    # persists summarised symbols into the base via incremental_save: base in, base out
    # (gate round 4 caught it reading the composed view and writing branch symbols to base)
    "summarize_repo.py",
}


def test_only_writers_call_load_index_directly():
    import re
    tools_dir = Path(__file__).resolve().parents[1] / "src" / "jcodemunch_mcp" / "tools"
    offenders = []
    for py in sorted(tools_dir.glob("*.py")):
        if py.name in LOAD_INDEX_ALLOWED:
            continue
        if re.search(r"\.load_index\(", py.read_text(encoding="utf-8", errors="replace")):
            offenders.append(py.name)
    assert offenders == [], offenders
    # _utils.py is allowlisted because load_view / _follow_checkout ARE the follow; nothing else
    # in it may load the base directly (gate round 4: resolve_fqn, a reader, hid behind the
    # allowlist and resolved PHP FQNs against base rows on a branch checkout)
    utils = (tools_dir / "_utils.py").read_text(encoding="utf-8", errors="replace")
    sites = [m.start() for m in re.finditer(r"= store\.load_index\(", utils)]
    owners = sorted({utils.rfind("\ndef ", 0, s) for s in sites})
    names = [re.match(r"\ndef (\w+)", utils[o:]).group(1) for o in owners]
    assert names == ["_follow_checkout", "load_view", "load_repo_index_or_error"], names


def _call_args(text: str, start: int) -> str:
    """The argument text of the call whose opening paren is at `start`."""
    depth, i = 0, start
    while i < len(text):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
        i += 1
    return text[start + 1:]


def test_every_content_read_in_tools_passes_the_view():
    """Finding 1 (gate round 1): `store.get_file_content(owner, name, path)` without `_index`
    resolves the BASE content dir; on a followed checkout that is the wrong bytes for every
    delta file. Every attribute-style content read in the tools package must pass the view,
    and plan_refactoring's wrapper must be handed one."""
    import re
    tools_dir = Path(__file__).resolve().parents[1] / "src" / "jcodemunch_mcp" / "tools"
    offenders = []
    for py in sorted(tools_dir.glob("*.py")):
        text = py.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"\.(get_file_content|get_symbol_content)\(", text):
            if "_index" not in _call_args(text, m.end() - 1):
                offenders.append(f"{py.name}:{text.count(chr(10), 0, m.start()) + 1}")
        for m in re.finditer(r"(?<!def )_get_file_content_safe\(", text):
            if not re.search(r"\bindex\b", _call_args(text, m.end() - 1)):
                offenders.append(f"{py.name}:{text.count(chr(10), 0, m.start()) + 1}")
    assert offenders == [], offenders


# -- gate round 2 on B2 part 2 (gate_20260907-183923): three more findings, all confirmed --

class _FlakyStore:
    """list_branches raises on the first call, answers afterwards."""
    def __init__(self, branches):
        self.calls = 0
        self.branches = branches
    def list_branches(self, owner, name):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient")
        return self.branches


def test_delta_branches_does_not_stash_a_transient_failure():
    # finding 2: a failed list_branches was stashed as frozenset() on the base object forever,
    # so a checkout with a real delta kept serving BASE bytes until the base was evicted
    from types import SimpleNamespace
    from jcodemunch_mcp.tools._utils import _delta_branches
    store = _FlakyStore([{"branch": "feature/x"}])
    base = SimpleNamespace()
    assert _delta_branches(store, OWNER, NAME, base) == frozenset()
    assert _delta_branches(store, OWNER, NAME, base) == frozenset({"feature/x"})


def test_base_head_never_falls_back_to_the_branch_head_on_a_composed_view():
    # finding 3: on a composed view, an unreadable branch meta fell back to index.git_head - the
    # BRANCH head - reproducing the empty-diff defect of round 1 on the error path
    from types import SimpleNamespace
    from jcodemunch_mcp.tools.get_changed_symbols import _base_head
    class _Broken:
        def list_branches(self, owner, name):
            raise RuntimeError("meta unreadable")
    composed = SimpleNamespace(branch="feature/x", git_head="bbb222")
    assert _base_head(_Broken(), OWNER, NAME, composed) == ""
    base = SimpleNamespace(branch="", git_head="aaa111")
    assert _base_head(_Broken(), OWNER, NAME, base) == "aaa111"


def test_every_session_result_cache_key_carries_the_view():
    """Finding 1 (gate round 2): the round-1 fix put the view identity into two cache keys; a
    reader with its own session cache (search_symbols) had none. Every session result cache key
    built in tools/ must name the view - `checkout_delta_branch(...)` or the index's `branch`."""
    import re
    tools_dir = Path(__file__).resolve().parents[1] / "src" / "jcodemunch_mcp" / "tools"
    offenders = []
    for py in sorted(tools_dir.glob("*.py")):
        text = py.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"\b_?result_cache_get\(", text):
            continue
        keys = list(re.finditer(r"\b_?(specific_key|cache_key)(?::[^=\n]+)?\s*=\s*\(", text))
        if not keys:
            offenders.append(f"{py.name}: no tuple key found")
        for m in keys:
            body = _call_args(text, m.end() - 1)
            if "checkout_delta_branch(" not in body and not re.search(r"\bbranch\b", body):
                offenders.append(f"{py.name}:{text.count(chr(10), 0, m.start()) + 1}")
    assert offenders == [], offenders
