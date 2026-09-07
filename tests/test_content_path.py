"""B2: the one public content resolver every retrieval tool uses.

Spec: Nexusmill docs/superpowers/specs/2026-09-06-jcm-branch-following-design.md, item 3.
Plan: Nexusmill docs/superpowers/plans/2026-09-07-jcm-branch-following.md, Tasks 1-2.

`content_path(owner, name, file_path, index)` returns the safe-resolved body path for
the view `index` describes: the branch dir only when `index.branch` is set AND the file
is a delta member, otherwise the base dir. Existence is NOT checked (a missing branch
body resolves to the missing branch path, never to base bytes); None only on traversal.
A structural guard keeps every tool on this resolver.
"""

import re
from pathlib import Path

from jcodemunch_mcp.storage import IndexStore
from jcodemunch_mcp.storage.sqlite_store import SQLiteIndexStore
from tests.test_branch_content_dir import BASE_MAIN, BASE_UTILS, BRANCH_MAIN, NAME, OWNER, _base, _delta

TOOLS_DIR = Path(__file__).resolve().parents[1] / "src" / "jcodemunch_mcp" / "tools"


class TestContentPath:
    def test_base_view_resolves_into_the_base_dir(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        base = store.load_index(OWNER, NAME)
        p = store.content_path(OWNER, NAME, "src/main.py", base)
        assert p == (store._content_dir(OWNER, NAME) / "src/main.py").resolve()
        assert p.read_text(encoding="utf-8") == BASE_MAIN

    def test_composed_view_resolves_delta_members_into_the_branch_dir_only(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)
        composed = store.load_index(OWNER, NAME, branch="feature/x")
        branch_dir = store._branch_content_dir(OWNER, NAME, "feature/x").resolve()
        base_dir = store._content_dir(OWNER, NAME).resolve()
        assert store.content_path(OWNER, NAME, "src/main.py", composed) == branch_dir / "src/main.py"
        assert store.content_path(OWNER, NAME, "src/main.py", composed).read_text(encoding="utf-8") == BRANCH_MAIN
        # unchanged file: base dir even though a branch dir exists
        assert store.content_path(OWNER, NAME, "src/utils.py", composed) == base_dir / "src/utils.py"
        assert store.content_path(OWNER, NAME, "src/utils.py", composed).read_text(encoding="utf-8") == BASE_UTILS

    def test_stray_branch_body_for_an_unchanged_file_is_ignored(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)
        composed = store.load_index(OWNER, NAME, branch="feature/x")
        stray = store._branch_content_dir(OWNER, NAME, "feature/x") / "src/utils.py"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("STRAY", encoding="utf-8")
        p = store.content_path(OWNER, NAME, "src/utils.py", composed)
        assert p.read_text(encoding="utf-8") == BASE_UTILS

    def test_missing_branch_body_resolves_to_the_branch_path_not_the_base_body(self, tmp_path):
        # fail closed: the caller sees a non-existent branch path, never base bytes
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)
        composed = store.load_index(OWNER, NAME, branch="feature/x")
        (store._branch_content_dir(OWNER, NAME, "feature/x") / "src/main.py").unlink()
        p = store.content_path(OWNER, NAME, "src/main.py", composed)
        assert p.parent == store._branch_content_dir(OWNER, NAME, "feature/x").resolve() / "src"
        assert not p.exists()

    def test_traversal_returns_none(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        base = store.load_index(OWNER, NAME)
        assert store.content_path(OWNER, NAME, "../../etc/passwd", base) is None

    def test_none_index_means_base_dir(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        p = store.content_path(OWNER, NAME, "src/main.py", None)
        assert p == (store._content_dir(OWNER, NAME) / "src/main.py").resolve()

    def test_facade_delegates(self, tmp_path):
        store = IndexStore(base_path=str(tmp_path))
        _base(store._sqlite)
        _delta(store._sqlite)
        composed = store.load_index(OWNER, NAME, branch="feature/x")
        assert store.content_path(OWNER, NAME, "src/main.py", composed) == \
            store._sqlite.content_path(OWNER, NAME, "src/main.py", composed)


class TestNoDirectContentDirReadersInTools:
    """Spec acceptance: all readers use content_path. Enforced structurally so a
    future tool cannot quietly join on the base dir again."""

    def test_only_the_index_folder_writer_touches_content_dir(self):
        offenders = []
        for py in sorted(TOOLS_DIR.glob("*.py")):
            text = py.read_text(encoding="utf-8", errors="replace")
            if re.search(r"\._content_dir\(", text):
                offenders.append(py.name)
        assert offenders == ["index_folder.py"], offenders


class TestGetSymbolToolWhenTheBodyCannotBeResolved:
    """Gate catches EV-044 (2026-09-07): after the migration `file_full_path` became
    Optional; both the content_cache_missing message and the token-savings getsize
    must survive a None (traversal) and a missing body without raising."""

    def _store_with_traversal_symbol(self, tmp_path):
        from jcodemunch_mcp.parser.symbols import Symbol
        store = SQLiteIndexStore(base_path=str(tmp_path))
        evil = Symbol(
            id="../evil.py:leak", file="../evil.py", name="leak", qualified_name="leak",
            kind="function", language="python", signature="def leak():", docstring="",
            summary="", decorators=[], keywords=[], parent=None, line=1, end_line=1,
            byte_offset=0, byte_length=5, content_hash="h",
        )
        store.save_index(
            owner=OWNER, name=NAME, source_files=["src/main.py", "../evil.py"],
            symbols=[evil], raw_files={"src/main.py": BASE_MAIN},
            file_hashes={"src/main.py": "h_main"}, git_head="aaa111",
            source_root=str(tmp_path / "nowhere"), file_languages={"src/main.py": "python"},
        )
        return store

    def test_traversal_symbol_reports_missing_content_instead_of_raising(self, tmp_path):
        from jcodemunch_mcp.tools.get_symbol import get_symbol_source
        self._store_with_traversal_symbol(tmp_path)
        res = get_symbol_source(f"{OWNER}/{NAME}", symbol_id="../evil.py:leak", storage_path=str(tmp_path))
        assert res.get("source_status") == "content_cache_missing", res
        assert "None" in res.get("source_unavailable_reason", ""), res

    def test_missing_base_body_reports_missing_content_instead_of_raising(self, tmp_path):
        from jcodemunch_mcp.tools.get_symbol import get_symbol_source
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        (store._content_dir(OWNER, NAME) / "src/main.py").unlink()
        res = get_symbol_source(f"{OWNER}/{NAME}", symbol_id="src/main.py:foo", storage_path=str(tmp_path))
        assert res.get("source_status") == "content_cache_missing", res
        assert "src/main.py" in res.get("source_unavailable_reason", ""), res
