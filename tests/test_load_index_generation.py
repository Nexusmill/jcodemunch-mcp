"""Gated findings 2026-09-05 (colibri review of storage/sqlite_store.py):

HIGH  - `load_index` read meta, symbols and files as three autocommit statements,
        so a writer committing mid-load produced a TORN CodeIndex (meta of one
        generation, rows of another) which was then cached under the post-write
        mtime as if it were fresh. `open_selective` already wraps its reads in one
        read transaction; the cold load did not.
MEDIUM - the write side built `IN (...)` lists with one placeholder per path and
        no chunking, while `_SELECT_CHUNK` exists precisely because
        SQLITE_MAX_VARIABLE_NUMBER is finite (32766 modern, 999 old builds).
        A delta wider than the limit raised "too many SQL variables".
"""

import sqlite3

import pytest

from jcodemunch_mcp.storage.sqlite_store import SQLiteIndexStore, _cache_clear

OWNER, NAME = "local", "generation-fixture"


def _symbol(file: str, name: str):
    from jcodemunch_mcp.parser.symbols import Symbol

    return Symbol(
        id=f"{file}::{name}#function",
        file=file,
        name=name,
        qualified_name=name,
        kind="function",
        language="python",
        signature=f"def {name}(): pass",
        summary="",
    )


def _seed(tmp_path) -> SQLiteIndexStore:
    _cache_clear()
    store = SQLiteIndexStore(base_path=str(tmp_path))
    store.save_index(
        owner=OWNER, name=NAME,
        source_files=["a.py"], symbols=[_symbol("a.py", "alpha")],
        raw_files={"a.py": "def alpha(): pass\n"}, git_head="gen1",
    )
    return store


def _names(index) -> set:
    return {s.get("name") if isinstance(s, dict) else getattr(s, "name", None) for s in index.symbols}


class TestColdLoadIsOneGeneration:
    def test_a_writer_committing_mid_load_never_yields_a_torn_index(self, tmp_path, monkeypatch):
        store = _seed(tmp_path)
        _cache_clear()  # force the cold path
        writer = SQLiteIndexStore(base_path=str(tmp_path))
        real_read_meta = store._read_meta
        fired = []

        def read_meta_then_let_a_writer_commit(conn):
            meta = real_read_meta(conn)  # the reader's first statement
            if not fired:
                fired.append(True)
                writer.incremental_save(
                    owner=OWNER, name=NAME,
                    changed_files=[], new_files=["b.py"], deleted_files=[],
                    new_symbols=[_symbol("b.py", "beta")],
                    raw_files={"b.py": "def beta(): pass\n"}, git_head="gen2",
                )
            return meta

        monkeypatch.setattr(store, "_read_meta", read_meta_then_let_a_writer_commit)

        first = store.load_index(OWNER, NAME)
        assert first is not None and fired
        # Whichever generation the load observed, it must be ONE generation.
        assert (first.git_head, "beta" in _names(first)) in {("gen1", False), ("gen2", True)}, (
            first.git_head, sorted(_names(first)),
        )
        # And the object handed out must not be cached as if it were current.
        second = store.load_index(OWNER, NAME)
        assert second.git_head == "gen2"
        assert "beta" in _names(second)

    def test_a_quiet_cold_load_is_still_cached(self, tmp_path, monkeypatch):
        store = _seed(tmp_path)
        _cache_clear()
        assert store.load_index(OWNER, NAME).git_head == "gen1"
        # A second load must be answered from the cache: no rows read.
        monkeypatch.setattr(store, "_read_meta", lambda conn: (_ for _ in ()).throw(AssertionError("re-read")))
        assert store.load_index(OWNER, NAME).git_head == "gen1"


def _variable_limit() -> int:
    """SQLITE_MAX_VARIABLE_NUMBER of the running SQLite. `Connection.getlimit`
    is Python 3.11+; the project floor is 3.10, where the compiled-in default
    (32766 since SQLite 3.32) is the honest fallback."""
    conn = sqlite3.connect(":memory:")
    try:
        getlimit = getattr(conn, "getlimit", None)
        if getlimit is None:
            return 32766
        return getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER)
    finally:
        conn.close()


class TestWriteSideInListsAreChunked:
    """Each test drives one delta wider than SQLITE_MAX_VARIABLE_NUMBER through a
    different `IN (...)` site (deleted files, changed files, branch-delta files)."""

    @staticmethod
    def _wide(tmp_path):
        store = _seed(tmp_path)
        n = _variable_limit() + 100
        paths = [f"pkg/f{i}.py" for i in range(n)]
        store.incremental_save(
            owner=OWNER, name=NAME,
            changed_files=[], new_files=paths, deleted_files=[],
            new_symbols=[_symbol(p, f"fn{i}") for i, p in enumerate(paths)],
            raw_files={}, file_hashes={p: "h" for p in paths}, git_head="gen2",
        )
        return store, paths

    def test_deleting_more_files_than_the_variable_limit(self, tmp_path):
        store, paths = self._wide(tmp_path)
        updated = store.incremental_save(
            owner=OWNER, name=NAME,
            changed_files=[], new_files=[], deleted_files=paths,
            new_symbols=[], raw_files={}, git_head="gen3",
        )
        assert updated is not None
        assert not any(p in updated.file_hashes for p in paths[::5000])
        assert "alpha" in _names(updated) and "fn0" not in _names(updated)

    def test_changing_more_files_than_the_variable_limit(self, tmp_path):
        store, paths = self._wide(tmp_path)
        updated = store.incremental_save(
            owner=OWNER, name=NAME,
            changed_files=paths, new_files=[], deleted_files=[],
            new_symbols=[_symbol(p, f"fn{i}_v2") for i, p in enumerate(paths)],
            raw_files={}, git_head="gen3",
        )
        assert updated is not None
        assert "fn0_v2" in _names(updated) and "fn0" not in _names(updated)

    def test_a_branch_delta_wider_than_the_variable_limit(self, tmp_path):
        store, paths = self._wide(tmp_path)
        store.save_branch_delta(
            owner=OWNER, name=NAME, branch="feature",
            changed_files=paths, new_files=[], deleted_files=[],
            new_symbols=[_symbol(p, f"fn{i}_b") for i, p in enumerate(paths)],
            raw_files={}, git_head="feat1", base_head="gen2",
        )
        view = store.load_index(OWNER, NAME, branch="feature")
        assert view is not None and "fn0_b" in _names(view)
