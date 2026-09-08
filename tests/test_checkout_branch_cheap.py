"""B2 spec item 1: the checkout resolver reads .git/HEAD and never spawns git.

Spec: Nexusmill docs/superpowers/specs/2026-09-06-jcm-branch-following-design.md.
Plan: Nexusmill docs/superpowers/plans/2026-09-07-jcm-branch-following.md, Task 4.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jcodemunch_mcp.tools.resolve_repo import _checkout_branch_cheap
from tests.test_branch_no_change_head import _git, _have_git

pytestmark = pytest.mark.skipif(not _have_git(), reason="git not available")


def _repo(tmp_path: Path, branch: str = "main") -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-b", branch)
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


def test_main_checkout(tmp_path):
    assert _checkout_branch_cheap(_repo(tmp_path)) == "main"


def test_slashed_branch_keeps_its_slash(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "gate/x")
    assert _checkout_branch_cheap(repo) == "gate/x"


def test_detached_head_is_none(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "--detach")
    assert _checkout_branch_cheap(repo) is None


def test_non_git_dir_is_none(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    assert _checkout_branch_cheap(d) is None


def test_missing_head_is_none(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".git" / "HEAD").unlink()
    assert _checkout_branch_cheap(repo) is None


def test_malformed_head_is_none(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".git" / "HEAD").write_text("ref: refs/tags/v1\n", encoding="utf-8")
    assert _checkout_branch_cheap(repo) is None
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/\n", encoding="utf-8")
    assert _checkout_branch_cheap(repo) is None


def test_malformed_gitdir_pointer_is_none(tmp_path):
    d = tmp_path / "wt"
    d.mkdir()
    (d / ".git").write_text("not a pointer\n", encoding="utf-8")
    assert _checkout_branch_cheap(d) is None
    (d / ".git").write_text("gitdir: \n", encoding="utf-8")
    assert _checkout_branch_cheap(d) is None


def test_linked_worktree_reports_its_own_branch(tmp_path):
    repo = _repo(tmp_path)
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", "feature/w", str(wt))
    assert _checkout_branch_cheap(wt) == "feature/w"
    assert _checkout_branch_cheap(repo) == "main"


def test_never_spawns_git(tmp_path, monkeypatch):
    repo = _repo(tmp_path)

    def boom(*a, **k):
        raise AssertionError("subprocess spawned")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    assert _checkout_branch_cheap(repo) == "main"
