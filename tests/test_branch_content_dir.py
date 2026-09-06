"""Branch-scoped content storage (Nexusmill spec 2026-09-06-jcm-branch-scoped-content-design, B1).

Before this tranche `_save_branch_delta_locked` wrote a branch's file bodies into the
BASE content dir, so a base-view read of a branch-modified file sliced branch bytes at
base offsets. Bodies for delta files now live in a sibling `<slug>@<branch-slug>` dir
and the two store readers pick the dir by delta MEMBERSHIP (`CodeIndex.delta_files`),
never by file existence, so a missing branch body fails closed.

Fixture rule: every branch body differs from its base body at offset 0.
"""

import re
from pathlib import Path
from unittest.mock import patch

from jcodemunch_mcp import config as _config
from jcodemunch_mcp.parser.symbols import Symbol
from jcodemunch_mcp.storage import process_locks
from jcodemunch_mcp.storage.sqlite_store import SQLiteIndexStore, _branch_slug

OWNER, NAME = "local", "test-repo"
BASE_MAIN = "def foo(): pass"                    # foo @ 0, len 15
BASE_UTILS = "def bar(): pass\ndef baz(): pass"  # bar @ 0 len 15, baz @ 16 len 15
BRANCH_MAIN = "XX = 1\ndef foo(): pass"          # differs at offset 0; foo @ 7, len 15
BRANCH_NEW = "def qux(): pass"                   # qux @ 0, len 15


def _sym(name: str, file: str, offset: int, length: int) -> Symbol:
    return Symbol(
        id=f"{file}:{name}", file=file, name=name, qualified_name=name, kind="function",
        language="python", signature=f"def {name}():", docstring="", summary="",
        decorators=[], keywords=[], parent=None, line=1, end_line=1,
        byte_offset=offset, byte_length=length, content_hash="h",
    )


def _base(store: SQLiteIndexStore):
    return store.save_index(
        owner=OWNER, name=NAME,
        source_files=["src/main.py", "src/utils.py"],
        symbols=[_sym("foo", "src/main.py", 0, 15), _sym("bar", "src/utils.py", 0, 15),
                 _sym("baz", "src/utils.py", 16, 15)],
        raw_files={"src/main.py": BASE_MAIN, "src/utils.py": BASE_UTILS},
        file_hashes={"src/main.py": "h_main", "src/utils.py": "h_utils"},
        git_head="aaa111", source_root="/tmp/test-repo",
        file_languages={"src/main.py": "python", "src/utils.py": "python"},
        branch="main",
    )


def _delta(store: SQLiteIndexStore, branch: str = "feature/x", **overrides):
    kwargs = dict(
        owner=OWNER, name=NAME, branch=branch,
        changed_files=["src/main.py"], new_files=["src/new.py"], deleted_files=[],
        new_symbols=[_sym("foo", "src/main.py", 7, 15), _sym("qux", "src/new.py", 0, 15)],
        raw_files={"src/main.py": BRANCH_MAIN, "src/new.py": BRANCH_NEW},
        git_head="bbb222", base_head="aaa111",
        file_hashes={"src/main.py": "h_main_v2", "src/new.py": "h_new"},
        file_languages={"src/main.py": "python", "src/new.py": "python"},
    )
    kwargs.update(overrides)
    store.save_branch_delta(**kwargs)


def _base_body(store: SQLiteIndexStore, rel: str) -> Path:
    return store._content_dir(OWNER, NAME) / rel


def _branch_body(store: SQLiteIndexStore, rel: str, branch: str = "feature/x") -> Path:
    return store._branch_content_dir(OWNER, NAME, branch) / rel


class TestBranchDirNaming:
    def test_slug_separates_slash_and_dash_variants_and_is_filesystem_safe(self):
        assert _branch_slug("feature/x") != _branch_slug("feature-x")
        for b in ("feature/x", "feature-x", "release/2026.09", "wip", "a" * 80):
            assert re.fullmatch(r"[A-Za-z0-9._-]+", _branch_slug(b)), _branch_slug(b)
        assert len(_branch_slug("a" * 80)) <= 49

    def test_branch_dir_is_a_sibling_of_the_base_dir_keyed_with_at(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        d = store._branch_content_dir(OWNER, NAME, "feature/x")
        assert d.parent == store._content_dir(OWNER, NAME).parent
        assert d.name.startswith(store._repo_slug(OWNER, NAME) + "@")
        assert "@" not in store._repo_slug(OWNER, NAME)


class TestDeltaMembership:
    def test_composed_index_carries_delta_files_and_the_base_does_not(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)
        composed = store.load_index(OWNER, NAME, branch="feature/x")
        assert composed.delta_files == frozenset({"src/main.py", "src/new.py"})
        assert store.load_index(OWNER, NAME).delta_files == frozenset()


class TestDeltaWriter:
    def test_delta_bodies_go_to_the_branch_dir_and_base_bodies_are_untouched(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)
        assert _base_body(store, "src/main.py").read_bytes() == BASE_MAIN.encode()
        assert not _base_body(store, "src/new.py").exists()
        assert _branch_body(store, "src/main.py").read_bytes() == BRANCH_MAIN.encode()
        assert _branch_body(store, "src/new.py").read_bytes() == BRANCH_NEW.encode()
        assert not _branch_body(store, "src/utils.py").exists()

    def test_base_reads_stay_base_while_a_delta_exists(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)
        base = store.load_index(OWNER, NAME)
        assert store.get_symbol_content(OWNER, NAME, "src/main.py:foo", _index=base) == BASE_MAIN
        assert store.get_symbol_content(OWNER, NAME, "src/main.py:foo") == BASE_MAIN
        assert store.get_file_content(OWNER, NAME, "src/main.py", _index=base) == BASE_MAIN
        assert store.get_file_content(OWNER, NAME, "src/new.py", _index=base) is None

    def test_deleting_a_file_removes_its_branch_body(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)
        _delta(store, changed_files=[], new_files=[], deleted_files=["src/new.py"],
               new_symbols=[], raw_files={}, file_hashes={}, file_languages={})
        assert not _branch_body(store, "src/new.py").exists()
        assert _branch_body(store, "src/main.py").exists()

    def test_replace_all_drops_rows_for_files_no_longer_in_the_delta(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)  # rows: src/main.py (modify), src/new.py (add)
        _delta(store, changed_files=[], new_files=["src/new.py"],
               new_symbols=[_sym("qux", "src/new.py", 0, 15)],
               raw_files={"src/new.py": BRANCH_NEW}, file_hashes={"src/new.py": "h_new"},
               file_languages={"src/new.py": "python"}, replace_all=True)
        rows = {e["file"] for e in store.load_branch_delta(OWNER, NAME, "feature/x")["files"]}
        assert rows == {"src/new.py"}
        # The reverted file is no longer a delta file, so its reads come from the base.
        composed = store.load_index(OWNER, NAME, branch="feature/x")
        assert "src/main.py" not in composed.delta_files
        assert store.get_file_content(OWNER, NAME, "src/main.py", _index=composed) == BASE_MAIN

    def test_default_save_keeps_rows_for_untouched_files(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)
        _delta(store, changed_files=[], new_files=["src/new.py"],
               new_symbols=[_sym("qux", "src/new.py", 0, 15)],
               raw_files={"src/new.py": BRANCH_NEW}, file_hashes={"src/new.py": "h_new"},
               file_languages={"src/new.py": "python"})
        rows = {e["file"] for e in store.load_branch_delta(OWNER, NAME, "feature/x")["files"]}
        assert rows == {"src/main.py", "src/new.py"}

    def test_replace_all_unlinks_the_bodies_of_files_that_dropped_out(self, tmp_path):
        # Gate catch 2026-09-06 (gate_20260906-142613, LOW): a dropped row's stale
        # body could be served later if the file re-entered the delta and its
        # fresh write was skipped or failed. The store removes it at drop-out.
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)
        _delta(store, changed_files=[], new_files=["src/new.py"],
               new_symbols=[_sym("qux", "src/new.py", 0, 15)],
               raw_files={"src/new.py": BRANCH_NEW}, file_hashes={"src/new.py": "h_new"},
               file_languages={"src/new.py": "python"}, replace_all=True)
        assert not _branch_body(store, "src/main.py").exists()
        assert _branch_body(store, "src/new.py").exists()


class TestReaders:
    def test_composed_reads_use_the_branch_dir_for_delta_files_only(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)
        composed = store.load_index(OWNER, NAME, branch="feature/x")
        # branch offsets over branch bytes
        assert store.get_symbol_content(OWNER, NAME, "src/main.py:foo", _index=composed) == "def foo(): pass"
        assert store.get_file_content(OWNER, NAME, "src/main.py", _index=composed) == BRANCH_MAIN
        assert store.get_file_content(OWNER, NAME, "src/new.py", _index=composed) == BRANCH_NEW
        assert store.get_symbol_content(OWNER, NAME, "src/new.py:qux", _index=composed) == BRANCH_NEW
        # unchanged file: the base body
        assert store.get_symbol_content(OWNER, NAME, "src/utils.py:baz", _index=composed) == "def baz(): pass"
        assert store.get_file_content(OWNER, NAME, "src/utils.py", _index=composed) == BASE_UTILS

    def test_missing_branch_body_fails_closed(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)
        _branch_body(store, "src/main.py").unlink()  # write failed after the row commit
        composed = store.load_index(OWNER, NAME, branch="feature/x")
        assert store.get_symbol_content(OWNER, NAME, "src/main.py:foo", _index=composed) is None
        assert store.get_file_content(OWNER, NAME, "src/main.py", _index=composed) is None
        # never base bytes at branch offsets; the base view itself is intact
        base = store.load_index(OWNER, NAME)
        assert store.get_file_content(OWNER, NAME, "src/main.py", _index=base) == BASE_MAIN

    def test_metadata_only_mode_writes_no_branch_body_and_reads_none(self, tmp_path):
        original = _config._GLOBAL_CONFIG.copy()
        _config._GLOBAL_CONFIG["cache_mode"] = "metadata_only"
        try:
            store = SQLiteIndexStore(base_path=str(tmp_path))
            _base(store)
            _delta(store)
            branch_dir = store._branch_content_dir(OWNER, NAME, "feature/x")
            assert not branch_dir.exists() or not any(p.is_file() for p in branch_dir.rglob("*"))
            composed = store.load_index(OWNER, NAME, branch="feature/x")
            assert store.get_file_content(OWNER, NAME, "src/main.py", _index=composed) is None
            assert store.get_file_content(OWNER, NAME, "src/main.py", _index=store.load_index(OWNER, NAME)) is None
        finally:
            _config._GLOBAL_CONFIG.clear()
            _config._GLOBAL_CONFIG.update(original)


class TestCleanup:
    def test_delete_branch_delta_removes_the_branch_dir(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)
        assert store.delete_branch_delta(OWNER, NAME, "feature/x") is True
        assert not store._branch_content_dir(OWNER, NAME, "feature/x").exists()
        assert _base_body(store, "src/main.py").exists()

    def test_delete_branch_delta_runs_under_the_indexwrite_lock(self, tmp_path):
        # Gate catch 2026-09-06 (gate_20260906-142613, LOW): the branch-dir rmtree
        # must not race a locked save_branch_delta that has committed rows and
        # is still writing bodies. Idiom: tests/test_v1_108_105.py lock spy.
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store)
        calls: list = []
        real = process_locks.held

        def spy(name, target, root, **kw):
            calls.append((name, target))
            return real(name, target, root, **kw)

        with patch.object(process_locks, "held", side_effect=spy):
            assert store.delete_branch_delta(OWNER, NAME, "feature/x") is True
        assert ("indexwrite", f"{OWNER}/{NAME}") in calls

    def test_delete_index_removes_every_branch_dir(self, tmp_path):
        store = SQLiteIndexStore(base_path=str(tmp_path))
        _base(store)
        _delta(store, branch="feature/x")
        _delta(store, branch="feature-x")
        assert store.delete_index(OWNER, NAME) is True
        assert list(Path(str(tmp_path)).glob(store._repo_slug(OWNER, NAME) + "@*")) == []
        assert not store._content_dir(OWNER, NAME).exists()
