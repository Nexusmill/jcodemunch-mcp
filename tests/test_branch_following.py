"""B2 acceptance (spec 2026-09-06-jcm-branch-following): retrieval follows the checkout.

Plan: Nexusmill docs/superpowers/plans/2026-09-07-jcm-branch-following.md, Task 5.

Every test builds a REAL git checkout whose branch bytes differ from the base
bytes at offset 0 (BRANCH_APP starts with '# feature', BASE_APP with 'def app').
"""
from __future__ import annotations

import subprocess

import pytest

from jcodemunch_mcp.retrieval.freshness import FreshnessProbe, _clear_head_cache
from jcodemunch_mcp.storage import IndexStore
from jcodemunch_mcp.tools._utils import load_repo_index_or_error
from jcodemunch_mcp.tools.get_symbol import get_symbol_source
from jcodemunch_mcp.tools.index_folder import index_folder
from jcodemunch_mcp.tools.search_text import search_text
from tests.test_branch_content_walk import BASE_APP, BASE_UTIL, BRANCH_APP, BRANCH_NEW, _seed
from tests.test_branch_no_change_head import _git, _have_git

pytestmark = pytest.mark.skipif(not _have_git(), reason="git not available")


def _head(repo) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True,
                          text=True, check=True).stdout.strip()


def _on_branch(repo, branch: str) -> str:
    """Create `branch` with BRANCH_APP + new.py, commit, return its HEAD sha."""
    _git(repo, "checkout", "-q", "-b", branch)
    (repo / "app.py").write_text(BRANCH_APP, newline="\n")
    (repo / "new.py").write_text(BRANCH_NEW, newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "branch work")
    return _head(repo)


def _index_branch(repo, store_path) -> dict:
    res = index_folder(path=str(repo), use_ai_summaries=False, storage_path=store_path,
                       incremental=False, identity_mode="local")
    assert res.get("success") is True, res
    return res


def _setup(tmp_path, branch: str = "feature"):
    repo, store_path, owner, name = _seed(tmp_path)
    base_head = _head(repo)
    branch_head = _on_branch(repo, branch)
    res = _index_branch(repo, store_path)
    assert res.get("branch") == branch, res
    _clear_head_cache()
    return repo, store_path, f"{owner}/{name}", owner, name, base_head, branch_head


def _hits(res: dict) -> set:
    return {r["file"] for r in res.get("results", [])}


class TestFollowing:
    def test_omitted_branch_selects_the_matching_composed_view(self, tmp_path):
        repo, sp, rid, owner, name, _, _ = _setup(tmp_path)
        idx, err, _ = load_repo_index_or_error(rid, sp)
        assert err is None
        assert idx.branch == "feature"
        assert idx.delta_files == frozenset({"app.py", "new.py"})

    def test_gate_side_branch_serves_gate_bytes_not_base_bytes(self, tmp_path):
        repo, sp, rid, owner, name, _, _ = _setup(tmp_path, branch="gate/x")
        idx, err, _ = load_repo_index_or_error(rid, sp)
        assert err is None and idx.branch == "gate/x"
        store = IndexStore(base_path=sp)
        assert store.get_file_content(owner, name, "app.py", _index=idx) == BRANCH_APP
        # through a real reader: the branch-only token is found, in app.py
        assert "app.py" in _hits(search_text(rid, "# feature", storage_path=sp))
        assert "new.py" in _hits(search_text(rid, "def new", storage_path=sp))

    def test_explicit_main_is_deterministic_regardless_of_checkout(self, tmp_path):
        repo, sp, rid, owner, name, _, _ = _setup(tmp_path)
        idx, err, _ = load_repo_index_or_error(rid, sp, branch="main")
        assert err is None
        assert idx.delta_files == frozenset()
        store = IndexStore(base_path=sp)
        assert store.get_file_content(owner, name, "app.py", _index=idx) == BASE_APP

    def test_detached_checkout_falls_back_to_the_base_view(self, tmp_path):
        repo, sp, rid, owner, name, _, _ = _setup(tmp_path)
        _git(repo, "checkout", "-q", "--detach")
        _clear_head_cache()
        idx, err, _ = load_repo_index_or_error(rid, sp)
        assert err is None
        assert idx.delta_files == frozenset()
        assert IndexStore(base_path=sp).get_file_content(owner, name, "app.py", _index=idx) == BASE_APP

    def test_non_git_source_root_falls_back_to_the_base_view(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        (plain / "app.py").write_text(BASE_APP, newline="\n")
        sp = str(tmp_path / "idx")
        res = index_folder(path=str(plain), use_ai_summaries=False, storage_path=sp,
                           incremental=True, identity_mode="local")
        assert res.get("success") is True, res
        owner, name = res["repo"].split("/", 1)
        store = IndexStore(base_path=sp)
        # a delta exists, but nothing in the checkout can select it
        store.save_branch_delta(owner=owner, name=name, branch="feature", changed_files=["app.py"],
                                new_files=[], deleted_files=[], new_symbols=[],
                                raw_files={"app.py": BRANCH_APP}, git_head="b" * 40,
                                base_head="", file_hashes={"app.py": "h2"},
                                file_languages={"app.py": "python"})
        idx, err, _ = load_repo_index_or_error(res["repo"], sp)
        assert err is None
        assert idx.delta_files == frozenset()
        assert store.get_file_content(owner, name, "app.py", _index=idx) == BASE_APP

    def test_checkout_without_a_delta_stays_on_the_base_view(self, tmp_path):
        repo, sp, rid, owner, name, _, _ = _setup(tmp_path)
        _git(repo, "checkout", "-q", "-b", "other")  # never indexed
        _clear_head_cache()
        idx, err, _ = load_repo_index_or_error(rid, sp)
        assert err is None
        assert idx.branch != "other" and idx.delta_files == frozenset()


class TestReadersOnTheComposedView:
    def test_unchanged_file_returns_base_bytes_even_with_a_stray_branch_body(self, tmp_path):
        repo, sp, rid, owner, name, _, _ = _setup(tmp_path)
        store = IndexStore(base_path=sp)
        stray = store._branch_content_dir(owner, name, "feature") / "util.py"
        stray.write_text("# STRAYTOKEN\ndef util():\n    return 0\n", encoding="utf-8")
        assert "util.py" not in _hits(search_text(rid, "STRAYTOKEN", storage_path=sp))
        assert "util.py" in _hits(search_text(rid, "def util", storage_path=sp))
        idx, _, _ = load_repo_index_or_error(rid, sp)
        assert store.get_file_content(owner, name, "util.py", _index=idx) == BASE_UTIL

    def test_missing_branch_body_fails_closed(self, tmp_path):
        repo, sp, rid, owner, name, _, _ = _setup(tmp_path)
        store = IndexStore(base_path=sp)
        (store._branch_content_dir(owner, name, "feature") / "app.py").unlink()
        # neither branch nor base bytes are served for app.py
        assert "app.py" not in _hits(search_text(rid, "# feature", storage_path=sp))
        assert "app.py" not in _hits(search_text(rid, "def app", storage_path=sp))
        idx, _, _ = load_repo_index_or_error(rid, sp)
        assert store.get_file_content(owner, name, "app.py", _index=idx) is None

    def test_get_symbol_context_lines_come_from_the_branch_body(self, tmp_path):
        repo, sp, rid, owner, name, _, _ = _setup(tmp_path)
        idx, _, _ = load_repo_index_or_error(rid, sp)
        sid = next(s["id"] for s in idx.symbols if s["name"] == "extra")
        res = get_symbol_source(rid, symbol_id=sid, context_lines=3, storage_path=sp)
        assert res.get("source", "").startswith("def extra()"), res
        assert "return 1" in (res.get("context_before") or ""), res


class TestFreshnessAndCache:
    def test_composed_view_reports_the_branch_head_and_is_fresh_on_that_checkout(self, tmp_path):
        repo, sp, rid, owner, name, base_head, branch_head = _setup(tmp_path)
        idx, _, _ = load_repo_index_or_error(rid, sp)
        assert idx.git_head == branch_head != base_head
        probe = FreshnessProbe(idx.source_root, idx.indexed_at, idx.git_head, file_mtimes=idx.file_mtimes)
        assert probe.repo_freshness == "fresh"          # a property, not a method
        base, _, _ = load_repo_index_or_error(rid, sp, branch="main")
        assert base.git_head == base_head
        assert FreshnessProbe(base.source_root, base.indexed_at, base.git_head,
                              file_mtimes=base.file_mtimes).repo_freshness == "stale"

    def test_switching_base_branch_base_leaks_neither_view(self, tmp_path):
        repo, sp, rid, owner, name, _, _ = _setup(tmp_path)
        store = IndexStore(base_path=sp)
        on_branch, _, _ = load_repo_index_or_error(rid, sp)
        assert on_branch.branch == "feature"
        _git(repo, "checkout", "-q", "main")
        _clear_head_cache()
        on_main, _, _ = load_repo_index_or_error(rid, sp)
        assert on_main.delta_files == frozenset()
        assert store.get_file_content(owner, name, "app.py", _index=on_main) == BASE_APP
        _git(repo, "checkout", "-q", "feature")
        _clear_head_cache()
        again, _, _ = load_repo_index_or_error(rid, sp)
        assert again.branch == "feature"
        assert store.get_file_content(owner, name, "app.py", _index=again) == BRANCH_APP
        # the base object was never mutated into a branch view
        assert on_main.delta_files == frozenset() and on_main.branch != "feature"
        assert not (store._content_dir(owner, name) / "new.py").exists()

    def test_default_diff_baseline_is_the_base_head_on_a_followed_view(self, tmp_path):
        # finding 2 (gate round 1): the composed view's git_head is the BRANCH head, so the
        # default `since_sha` became branch_head..HEAD = empty - get_pr_risk_profile reported
        # risk 0.0 for the very branch it was asked about. The default must stay the base
        # branch's indexed sha (pre-B2 behaviour), so the diff spans the branch's work.
        from jcodemunch_mcp.tools.get_changed_symbols import get_changed_symbols
        repo, sp, rid, owner, name, base_head, branch_head = _setup(tmp_path)
        res = get_changed_symbols(rid, storage_path=sp)
        assert "error" not in res, res
        assert res["from_sha"] == base_head[:12], (res["from_sha"], base_head, branch_head)
        assert set(res["changed_files"]) == {"app.py", "new.py"}
        assert {s["name"] for s in res["added_symbols"]} == {"extra", "new"}

    def test_following_never_spawns_git(self, tmp_path, monkeypatch):
        repo, sp, rid, owner, name, _, _ = _setup(tmp_path)
        load_repo_index_or_error(rid, sp)  # warm the caches
        import jcodemunch_mcp.tools.resolve_repo as rr
        import jcodemunch_mcp.tools._utils as ut

        def boom(*a, **k):
            raise AssertionError("subprocess spawned on the retrieval path")

        monkeypatch.setattr(rr.subprocess, "run", boom, raising=False)
        monkeypatch.setattr(ut, "subprocess", type("S", (), {"run": boom}), raising=False)
        idx, err, _ = load_repo_index_or_error(rid, sp)
        assert err is None and idx.branch == "feature"
