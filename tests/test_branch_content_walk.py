"""index_folder / index_file end to end on a feature branch (Nexusmill spec
2026-09-06-jcm-branch-scoped-content-design, 5.8 items 8-12).

The streaming full walk (index_folder with incremental=False) used to write EVERY
walked file's body into the BASE content dir and hand save_branch_delta an empty
raw_files ("already written"). It now writes only hash-differing files, into the
branch's own dir, and replaces the branch's delta rows wholesale.
"""

from pathlib import Path

import pytest

from jcodemunch_mcp.reindex_state import WatcherChange
from jcodemunch_mcp.storage import IndexStore
from jcodemunch_mcp.tools.index_file import index_file
from jcodemunch_mcp.tools.index_folder import index_folder
from tests.test_branch_no_change_head import _git, _have_git

BASE_APP = "def app():\n    return 1\n"
BASE_UTIL = "def util():\n    return 0\n"
BRANCH_APP = "# feature\ndef app():\n    return 1\n\ndef extra():\n    return 2\n"  # differs at offset 0
BRANCH_NEW = "def new():\n    return 4\n"


def _seed(tmp_path: Path):
    """Git repo on `main` with app.py + util.py, indexed once (the base)."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text(BASE_APP, newline="\n")
    (repo / "util.py").write_text(BASE_UTIL, newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")
    store_path = str(tmp_path / "idx")
    first = index_folder(path=str(repo), use_ai_summaries=False, storage_path=store_path,
                         incremental=True, identity_mode="local")
    assert first.get("success") is True, first
    owner, name = first["repo"].split("/", 1)
    return repo, store_path, owner, name


def _on_feature(repo: Path, app: str = BRANCH_APP, new=BRANCH_NEW) -> None:
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "app.py").write_text(app, newline="\n")
    if new is not None:
        (repo / "new.py").write_text(new, newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "feature work")


def _dirs(store: IndexStore, owner: str, name: str):
    return store._content_dir(owner, name), store._branch_content_dir(owner, name, "feature")


def _delta_rows(store: IndexStore, owner: str, name: str) -> set:
    return {e["file"] for e in store._sqlite.load_branch_delta(owner, name, "feature")["files"]}


def _sym_id(index, symbol_name: str) -> str:
    return next(s["id"] for s in index.symbols if s["name"] == symbol_name)


@pytest.mark.skipif(not _have_git(), reason="git not available")
class TestFullWalkOnABranch:
    def test_full_walk_keeps_base_bodies_and_writes_only_delta_bodies_to_the_branch_dir(self, tmp_path):
        repo, store_path, owner, name = _seed(tmp_path)
        store = IndexStore(base_path=store_path)
        _on_feature(repo)
        res = index_folder(path=str(repo), use_ai_summaries=False, storage_path=store_path,
                           incremental=False, identity_mode="local")
        assert res.get("success") is True and res.get("branch") == "feature", res

        base_dir, branch_dir = _dirs(store, owner, name)
        assert (base_dir / "app.py").read_text(encoding="utf-8") == BASE_APP
        assert not (base_dir / "new.py").exists()
        assert (branch_dir / "app.py").read_text(encoding="utf-8") == BRANCH_APP
        assert (branch_dir / "new.py").read_text(encoding="utf-8") == BRANCH_NEW
        assert not (branch_dir / "util.py").exists()

        base = store.load_index(owner, name)
        composed = store.load_index(owner, name, branch="feature")
        assert composed.delta_files == frozenset({"app.py", "new.py"})
        assert store.get_file_content(owner, name, "app.py", _index=base) == BASE_APP
        assert store.get_file_content(owner, name, "app.py", _index=composed) == BRANCH_APP
        assert store.get_symbol_content(owner, name, _sym_id(base, "app"), _index=base).startswith("def app()")
        assert store.get_symbol_content(owner, name, _sym_id(composed, "extra"), _index=composed).startswith("def extra()")
        assert store.get_file_content(owner, name, "util.py", _index=composed) == BASE_UTIL

    def test_full_walk_after_a_revert_drops_the_stale_row_and_body(self, tmp_path):
        repo, store_path, owner, name = _seed(tmp_path)
        store = IndexStore(base_path=store_path)
        _on_feature(repo)
        res = index_folder(path=str(repo), use_ai_summaries=False, storage_path=store_path,
                           incremental=False, identity_mode="local")
        assert res.get("success") is True, res

        (repo / "app.py").write_text(BASE_APP, newline="\n")  # revert app.py; new.py stays
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "revert app.py")
        res = index_folder(path=str(repo), use_ai_summaries=False, storage_path=store_path,
                           incremental=False, identity_mode="local")
        assert res.get("success") is True, res

        assert _delta_rows(store, owner, name) == {"new.py"}
        _, branch_dir = _dirs(store, owner, name)
        assert not (branch_dir / "app.py").exists()
        assert (branch_dir / "new.py").exists()
        composed = store.load_index(owner, name, branch="feature")
        assert store.get_file_content(owner, name, "app.py", _index=composed) == BASE_APP

    def test_failed_walk_leaves_the_previous_delta_readable(self, tmp_path):
        # Gate catch 2026-09-06 (gate_20260906-144626, MEDIUM): wiping the branch
        # dir BEFORE the walk made a mid-walk failure sticky - the old rows survived,
        # their bodies did not, and the next incremental run saw "no changes".
        repo, store_path, owner, name = _seed(tmp_path)
        store = IndexStore(base_path=store_path)
        _on_feature(repo)
        res = index_folder(path=str(repo), use_ai_summaries=False, storage_path=store_path,
                           incremental=False, identity_mode="local")
        assert res.get("success") is True, res

        def boom(idx, total, rel):
            if rel == "app.py":  # first file of the per-file loop: nothing written yet
                raise RuntimeError("simulated failure mid-walk")

        try:
            res = index_folder(path=str(repo), use_ai_summaries=False, storage_path=store_path,
                               incremental=False, identity_mode="local", progress_cb=boom)
            assert res.get("success") is not True, res
        except RuntimeError:
            pass

        _, branch_dir = _dirs(store, owner, name)
        assert (branch_dir / "app.py").read_text(encoding="utf-8") == BRANCH_APP
        assert (branch_dir / "new.py").read_text(encoding="utf-8") == BRANCH_NEW
        composed = store.load_index(owner, name, branch="feature")
        assert store.get_file_content(owner, name, "app.py", _index=composed) == BRANCH_APP
        assert store.get_file_content(owner, name, "new.py", _index=composed) == BRANCH_NEW

    def test_subdir_full_walk_on_a_branch_is_refused(self, tmp_path):
        # Gate catch 2026-09-06 (gate_20260906-144626, MEDIUM): a subdir walk on a
        # branch covers only its prefix, so replace_all would drop every delta row
        # outside it and delta_deleted would mark the rest of the base as deleted.
        repo = tmp_path / "repo"
        (repo / "pkg").mkdir(parents=True)
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test")
        (repo / "app.py").write_text(BASE_APP, newline="\n")
        (repo / "pkg" / "mod.py").write_text("def mod():\n    return 5\n", newline="\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "initial")
        store_path = str(tmp_path / "idx")
        first = index_folder(path=str(repo), use_ai_summaries=False, storage_path=store_path,
                             incremental=True, identity_mode="git")
        assert first.get("success") is True, first

        _git(repo, "checkout", "-q", "-b", "feature")
        (repo / "pkg" / "mod.py").write_text("# feature\ndef mod():\n    return 5\n", newline="\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "feature work")
        res = index_folder(path=str(repo / "pkg"), use_ai_summaries=False, storage_path=store_path,
                           incremental=False, identity_mode="git")
        assert res.get("success") is False, res
        assert "branch" in res.get("error", "").lower() and "pkg" in res.get("error", ""), res
        # and the base index is untouched by the refused run
        store = IndexStore(base_path=store_path)
        owner, name = first["repo"].split("/", 1)
        assert store.load_index(owner, name).branch == "main"

    def test_base_mode_runs_create_no_branch_dir(self, tmp_path):
        repo, store_path, owner, name = _seed(tmp_path)
        store = IndexStore(base_path=store_path)
        (repo / "app.py").write_text(BRANCH_APP, newline="\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "change on main")
        for incremental in (True, False):
            res = index_folder(path=str(repo), use_ai_summaries=False, storage_path=store_path,
                               incremental=incremental, identity_mode="local")
            assert res.get("success") is True and "branch" not in res, res
        assert list(Path(store_path).glob("*@*")) == []
        assert (store._content_dir(owner, name) / "app.py").read_text(encoding="utf-8") == BRANCH_APP


@pytest.mark.skipif(not _have_git(), reason="git not available")
class TestIncrementalPathsOnABranch:
    """The three pass-through callers (incremental discovery, watcher fast path,
    index_file) hand raw_files to the store, which routes them. No production
    change here: these prove the routing end to end (spec 5.8 items 10-11)."""

    def test_incremental_discovery_on_feature_routes_bodies_to_the_branch_dir(self, tmp_path):
        repo, store_path, owner, name = _seed(tmp_path)
        store = IndexStore(base_path=store_path)
        _on_feature(repo)
        res = index_folder(path=str(repo), use_ai_summaries=False, storage_path=store_path,
                           incremental=True, identity_mode="local")
        assert res.get("success") is True and res.get("branch") == "feature", res
        base_dir, branch_dir = _dirs(store, owner, name)
        assert (base_dir / "app.py").read_text(encoding="utf-8") == BASE_APP
        assert (branch_dir / "app.py").read_text(encoding="utf-8") == BRANCH_APP
        assert (branch_dir / "new.py").read_text(encoding="utf-8") == BRANCH_NEW

    def test_watcher_fast_path_on_feature_routes_the_body_to_the_branch_dir(self, tmp_path):
        repo, store_path, owner, name = _seed(tmp_path)
        store = IndexStore(base_path=store_path)
        old_hash = store.load_index(owner, name).file_hashes["app.py"]
        _on_feature(repo, new=None)
        res = index_folder(path=str(repo), use_ai_summaries=False, storage_path=store_path,
                           incremental=True, identity_mode="local",
                           changed_paths=[WatcherChange("modified", str(repo / "app.py"), old_hash)])
        assert res.get("success") is True and res.get("fast_path") is True, res
        base_dir, branch_dir = _dirs(store, owner, name)
        assert (base_dir / "app.py").read_text(encoding="utf-8") == BASE_APP
        assert (branch_dir / "app.py").read_text(encoding="utf-8") == BRANCH_APP
        composed = store.load_index(owner, name, branch="feature")
        assert store.get_symbol_content(owner, name, _sym_id(composed, "extra"), _index=composed).startswith("def extra()")

    def test_index_file_on_feature_routes_the_body_to_the_branch_dir(self, tmp_path):
        repo, store_path, owner, name = _seed(tmp_path)
        store = IndexStore(base_path=store_path)
        _on_feature(repo, new=None)
        res = index_file(path=str(repo / "app.py"), use_ai_summaries=False, storage_path=store_path)
        assert res.get("success") is True, res
        base_dir, branch_dir = _dirs(store, owner, name)
        assert (base_dir / "app.py").read_text(encoding="utf-8") == BASE_APP
        assert (branch_dir / "app.py").read_text(encoding="utf-8") == BRANCH_APP
