"""Gated findings 2026-09-05 (colibri review of investigator/deletion_safety.py):

HIGH   - `_split_importers_by_liveness` classed every zero-importer file as dead.
         Scripts, bin/ entries, tests and `__main__.py` have zero importers BY
         CONSTRUCTION yet run, so a symbol imported only by `scripts/migrate.js`
         reached SATISFIED with a "deletion cluster" and the verdict could be SAFE.
MEDIUM - the `deletion_cluster` override replaced the "Do not delete" action even
         under an UNSAFE verdict.
MEDIUM - a `search_text` error payload collapsed into SATISFIED ("appears only in
         its own file") instead of UNESTABLISHED, the invariant the module states.

Own fixture (mirrors tests/test_investigator_deletion_safety.py's shape) so the
A/B fixture there stays byte-identical.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jcodemunch_mcp.investigator import SATISFIED, UNESTABLISHED, investigate_deletion_safety
from jcodemunch_mcp.investigator.deletion_safety import UNSAFE
from jcodemunch_mcp.tools.index_folder import index_folder

FIXTURE = {
    "package.json": '{"name":"fx","version":"1.0.0","type":"module","main":"src/main.js"}',
    # app.js keeps main.js LIVE (one importer); main.js only MENTIONS formatThing.
    "src/app.js": "import { boot } from './main.js';\nexport const started = boot();\n",
    "src/main.js": (
        "// string dispatch table: formatThing is looked up by name at runtime\n"
        "export function boot() { return 'formatThing'; }\n"
    ),
    "src/lib/util.js": "export function formatThing(n) { return n; }\n",
    # deadUser.js imports formatThing and nothing imports deadUser.js.
    "src/dead/deadUser.js": (
        "import { formatThing } from '../lib/util.js';\n"
        "export function useIt() { return formatThing(1); }\n"
    ),
    # runMigration is imported ONLY by a script nobody imports.
    "src/lib/migrations.js": "export function runMigration() { return 1; }\n",
    "scripts/migrate.js": (
        "import { runMigration } from '../src/lib/migrations.js';\nrunMigration();\n"
    ),
}


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> tuple[str, str]:
    root = tmp_path_factory.mktemp("deletion_roots_fx")
    for rel, body in FIXTURE.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    storage = str(Path(root) / ".index")
    res = index_folder(str(root), use_ai_summaries=False, storage_path=storage)
    assert res.get("success"), res
    return res.get("repo", str(root)), storage


def _ob(result: dict, name: str) -> dict:
    for o in result["obligations"]:
        if o["obligation"] == name:
            return o
    raise AssertionError(f"obligation {name!r} missing from {result['obligations']}")


class TestRootImportersAreLive:
    def test_a_symbol_imported_only_by_a_script_is_unsafe_to_delete(self, repo):
        repo_id, storage = repo
        r = investigate_deletion_safety(repo_id, "runMigration", storage_path=storage)
        assert r["verdict"] == UNSAFE, r
        assert "export_not_imported" in r["refuted_obligations"], r["obligations"]
        assert any("scripts/migrate.js" in e for e in _ob(r, "export_not_imported")["evidence"])
        assert not r.get("deletion_cluster"), "a script is a root, not a dead importer"


class TestClusterNeverOverridesDoNotDelete:
    def test_an_unsafe_verdict_keeps_its_action_even_with_a_dead_cluster(self, repo):
        repo_id, storage = repo
        r = investigate_deletion_safety(repo_id, "formatThing", storage_path=storage)
        assert r["verdict"] == UNSAFE, r  # main.js (live) mentions the name
        assert r["recommended_next_action"].startswith("Do not delete"), r["recommended_next_action"]
        # The cluster is still reported - as information, not as the action.
        assert any("deadUser" in f for f in r.get("deletion_cluster", []))


class TestTextSweepErrorsStayUnestablished:
    def test_a_failed_sweep_is_not_absence(self, repo, monkeypatch):
        import jcodemunch_mcp.tools.search_text as search_text_module

        repo_id, storage = repo
        monkeypatch.setattr(
            search_text_module, "search_text", lambda *a, **k: {"error": "index vanished mid-investigation"}
        )
        r = investigate_deletion_safety(repo_id, "runMigration", storage_path=storage)
        text_obs = [o for o in r["obligations"] if "text" in o["obligation"]]
        assert text_obs, [o["obligation"] for o in r["obligations"]]
        for o in text_obs:
            assert o["status"] == UNESTABLISHED, o
            assert o["status"] != SATISFIED
