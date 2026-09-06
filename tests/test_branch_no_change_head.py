"""Gated finding 2026-09-05 (colibri review of tools/index_folder.py, HIGH):
the no-change return paths wrote the BRANCH's git_head into the BASE index.

`_refresh_git_head_if_advanced` (both call sites) and the watcher fast path's
mtime-only block always called `store.incremental_save`, which writes the base
index's meta, even when the run was a branch-delta run. On a feature branch a
commit that touches only non-indexed files therefore stamped the branch HEAD into
the base index: the base was "at" a commit it was never indexed at, every later
branch load warned the delta was stale (`base_head != index.git_head`), and the
branch's own git_head never advanced. Idiom follows tests/test_v1_108_56.py (#330).
"""

import shutil
import subprocess
import types
from pathlib import Path

import pytest

from jcodemunch_mcp.reindex_state import WatcherChange
from jcodemunch_mcp.storage import IndexStore
from jcodemunch_mcp.tools.index_folder import _refresh_git_head_if_advanced, index_folder


def _have_git() -> bool:
    return shutil.which("git") is not None


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)


def _head(repo: Path) -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), check=True, capture_output=True, text=True,
    )
    return out.stdout.strip()


def _seed_on_main(tmp_path: Path):
    """Git repo on branch `main` with one indexed file, indexed once (base index)."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text("def app():\n    return 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")
    store_path = str(tmp_path / "idx")
    first = index_folder(
        path=str(repo), use_ai_summaries=False, storage_path=store_path,
        incremental=True, identity_mode="local",
    )
    assert first.get("success") is True, first
    owner, name = first["repo"].split("/", 1)
    return repo, store_path, owner, name


def _commit_non_indexed_file_on_new_branch(repo: Path, branch: str = "feature") -> str:
    _git(repo, "checkout", "-q", "-b", branch)
    (repo / "LICENSE").write_text("hello world\n")  # extensionless: outside every language map
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "license only")
    return _head(repo)


def _branch_meta(store: IndexStore, owner: str, name: str, branch: str):
    return next((b for b in store.list_branches(owner, name) if b["branch"] == branch), None)


@pytest.mark.skipif(not _have_git(), reason="git not available")
class TestBaseBranchIsPersisted:
    """Root cause behind the finding: save_index wrote meta `base_branch` from
    `CodeIndex.branch`, which nothing ever set, and `_build_index_from_rows` never
    read it back — so every loaded base carried branch == "" and index_folder's
    "base IS this branch" fallback made delta mode unreachable on the first switch.
    """

    def test_first_full_index_records_the_base_branch(self, tmp_path):
        repo, store_path, owner, name = _seed_on_main(tmp_path)
        store = IndexStore(base_path=store_path)
        assert store.load_index(owner, name).branch == "main"


@pytest.mark.skipif(not _have_git(), reason="git not available")
class TestWarmCacheKeepsBaseBranch:
    """Gate round-1 finding (2026-09-06): the warm incremental path rebuilds the
    base through `_patch_index_from_delta`, which constructed a CodeIndex without
    `branch=` and re-cached it - so one base-mode incremental_save in a long-lived
    process erased the branch and re-armed the "base IS this branch" fallback.
    """

    def _commit_non_indexed_file_on_main(self, repo: Path) -> str:
        (repo / "LICENSE").write_text("on main\n")  # differs from the feature-branch content
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "license only, still on main")
        return _head(repo)

    def test_base_mode_incremental_save_keeps_the_branch_in_process(self, tmp_path):
        repo, store_path, owner, name = _seed_on_main(tmp_path)
        store = IndexStore(base_path=store_path)
        assert store.load_index(owner, name).branch == "main"

        head2 = self._commit_non_indexed_file_on_main(repo)
        res = index_folder(  # no-change run on the base: helper -> incremental_save (warm cache)
            path=str(repo), use_ai_summaries=False, storage_path=store_path,
            incremental=True, identity_mode="local",
        )
        assert res.get("success") is True, res
        base = store.load_index(owner, name)
        assert base.git_head == head2
        assert base.branch == "main"

    def test_branch_switch_after_warm_incremental_save_still_takes_delta_mode(self, tmp_path):
        repo, store_path, owner, name = _seed_on_main(tmp_path)
        store = IndexStore(base_path=store_path)
        head_main = self._commit_non_indexed_file_on_main(repo)
        index_folder(
            path=str(repo), use_ai_summaries=False, storage_path=store_path,
            incremental=True, identity_mode="local",
        )
        assert store.load_index(owner, name).git_head == head_main

        head_feature = _commit_non_indexed_file_on_new_branch(repo)
        res = index_folder(
            path=str(repo), use_ai_summaries=False, storage_path=store_path,
            incremental=True, identity_mode="local",
        )
        assert res.get("success") is True, res
        assert store.load_index(owner, name).git_head == head_main
        meta = _branch_meta(store, owner, name, "feature")
        assert meta is not None and meta["git_head"] == head_feature, store.list_branches(owner, name)


@pytest.mark.skipif(not _have_git(), reason="git not available")
class TestNewlyLiveBranchDeltaPathsLeaveTheBaseAlone:
    """Gate round-2 findings (2026-09-06): persisting the base branch makes the
    branch-delta paths reachable for the first time, and two of them still wrote
    to the BASE: the watcher fast path's deferred-summarizer thread saved the
    branch's summarized symbols through a branch-less incremental_save, and both
    delta paths rewrote the base's coverage contract with the branch's walk.
    """

    def test_fast_path_delta_does_not_start_the_base_summarizer_thread(self, tmp_path, monkeypatch):
        import jcodemunch_mcp.tools.index_folder as index_folder_module

        repo, store_path, owner, name = _seed_on_main(tmp_path)
        store = IndexStore(base_path=store_path)
        old_hash = store.load_index(owner, name).file_hashes["app.py"]
        started: list = []

        class _RecordingThread:
            def __init__(self, *args, **kwargs):
                started.append(kwargs.get("name"))

            def start(self):
                pass

        # index_folder only reaches threading via `threading.Thread`.
        monkeypatch.setattr(index_folder_module, "threading", types.SimpleNamespace(Thread=_RecordingThread))

        _git(repo, "checkout", "-q", "-b", "feature")
        (repo / "app.py").write_text("def app():\n    return 1\n\ndef extra():\n    return 2\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "real change on feature")
        res = index_folder(
            path=str(repo), use_ai_summaries=True, storage_path=store_path,
            incremental=True, identity_mode="local",
            changed_paths=[WatcherChange("modified", str(repo / "app.py"), old_hash)],
        )
        assert res.get("success") is True, res
        assert res.get("fast_path") is True, res
        assert started == [], "a branch-delta fast-path run must not summarize into the base"
        # The base index knows nothing of the branch's new symbol.
        assert all(s.get("name") != "extra" for s in store.load_index(owner, name).symbols)

    def test_delta_full_walk_does_not_rewrite_base_coverage(self, tmp_path):
        repo, store_path, owner, name = _seed_on_main(tmp_path)
        store = IndexStore(base_path=store_path)
        before = dict(store.load_index(owner, name).coverage or {})
        assert before, "the base save must have recorded a coverage contract"

        _git(repo, "checkout", "-q", "-b", "feature")
        (repo / "extra.py").write_text("def extra():\n    return 2\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "new file on feature")
        res = index_folder(
            path=str(repo), use_ai_summaries=False, storage_path=store_path,
            incremental=True, identity_mode="local",
        )
        assert res.get("success") is True, res
        assert res.get("new") == 1, res
        assert dict(store.load_index(owner, name).coverage or {}) == before


@pytest.mark.skipif(not _have_git(), reason="git not available")
class TestNoChangeRunOnBranchKeepsBaseHead:
    def test_full_walk_no_change_on_branch_advances_branch_head_not_base(self, tmp_path):
        repo, store_path, owner, name = _seed_on_main(tmp_path)
        store = IndexStore(base_path=store_path)
        head_main = store.load_index(owner, name).git_head
        assert head_main == _head(repo)

        head_feature = _commit_non_indexed_file_on_new_branch(repo)
        res = index_folder(
            path=str(repo), use_ai_summaries=False, storage_path=store_path,
            incremental=True, identity_mode="local",
        )
        assert res.get("success") is True, res
        assert (res.get("changed", 0), res.get("new", 0), res.get("deleted", 0)) == (0, 0, 0)

        # The base index was indexed at head_main and must still say so.
        assert store.load_index(owner, name).git_head == head_main
        # The branch's own freshness marker is what advances.
        meta = _branch_meta(store, owner, name, "feature")
        assert meta is not None and meta["git_head"] == head_feature, store.list_branches(owner, name)
        assert meta["base_head"] == head_main
        assert store.load_index(owner, name, branch="feature").git_head == head_feature

    def test_watcher_fast_path_mtime_only_on_branch_keeps_base_head(self, tmp_path):
        repo, store_path, owner, name = _seed_on_main(tmp_path)
        store = IndexStore(base_path=store_path)
        head_main = store.load_index(owner, name).git_head
        old_hash = store.load_index(owner, name).file_hashes["app.py"]

        head_feature = _commit_non_indexed_file_on_new_branch(repo)
        # A "modified" event whose content is unchanged: the fast path's mtime-only block.
        (repo / "app.py").touch()
        res = index_folder(
            path=str(repo), use_ai_summaries=False, storage_path=store_path,
            incremental=True, identity_mode="local",
            changed_paths=[WatcherChange("modified", str(repo / "app.py"), old_hash)],
        )
        assert res.get("success") is True, res
        assert res.get("message") == "No changes detected", res

        assert store.load_index(owner, name).git_head == head_main
        meta = _branch_meta(store, owner, name, "feature")
        assert meta is not None and meta["git_head"] == head_feature, store.list_branches(owner, name)


@pytest.mark.skipif(not _have_git(), reason="git not available")
class TestRefreshHelperBranchMode:
    def test_helper_with_branch_writes_branch_meta_and_preserves_base_head(self, tmp_path):
        repo, store_path, owner, name = _seed_on_main(tmp_path)
        store = IndexStore(base_path=store_path)
        head_main = store.load_index(owner, name).git_head
        head_feature = _commit_non_indexed_file_on_new_branch(repo)

        # An existing delta with its base_head recorded must keep that base_head.
        store.save_branch_delta(
            owner=owner, name=name, branch="feature",
            changed_files=[], new_files=[], deleted_files=[], new_symbols=[], raw_files={},
            git_head="stale000", base_head=head_main,
        )
        wrote = _refresh_git_head_if_advanced(store, owner, name, repo, "stale000", branch="feature")
        assert wrote == head_feature
        meta = _branch_meta(store, owner, name, "feature")
        assert meta["git_head"] == head_feature
        assert meta["base_head"] == head_main
        assert store.load_index(owner, name).git_head == head_main

        # Idempotent: already current -> no write, returns "".
        assert _refresh_git_head_if_advanced(store, owner, name, repo, head_feature, branch="feature") == ""

    def test_helper_with_branch_and_no_delta_uses_base_head_of_base_index(self, tmp_path):
        repo, store_path, owner, name = _seed_on_main(tmp_path)
        store = IndexStore(base_path=store_path)
        head_main = store.load_index(owner, name).git_head
        head_feature = _commit_non_indexed_file_on_new_branch(repo)

        wrote = _refresh_git_head_if_advanced(store, owner, name, repo, head_main, branch="feature")
        assert wrote == head_feature
        meta = _branch_meta(store, owner, name, "feature")
        assert meta is not None
        assert meta["git_head"] == head_feature
        assert meta["base_head"] == head_main
        assert store.load_index(owner, name).git_head == head_main
