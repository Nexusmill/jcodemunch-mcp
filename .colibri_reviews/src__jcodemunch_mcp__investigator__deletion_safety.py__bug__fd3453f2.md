# Colibri review — src/jcodemunch_mcp/investigator/deletion_safety.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\investigator\deletion_safety.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `z-ai/glm-5.3-flash` review, `.colibri_reviews/_external_raw/jcm__deletion_safety.py__z-ai-glm-5.3-flash.md`)
- sha256: `fd3453f2c83e283aa493c7155d195a2f5f9a0e3994c0c103b3b0ada575aee76e` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
Two confirmed ways a deletion verdict can be wrong in the unsafe direction; this is the module whose whole contract is not doing that.

## Bugs & vulnerabilities
**[HIGH] Zero-importer files are classed dead with no entry-point check — CONFIRMED** - `line 116-128, 304-316`
- What: `_split_importers_by_liveness` puts every file with `importer_count == 0` into `dead`. Scripts, `__main__.py`, tests and `bin/` entries have zero importers BY CONSTRUCTION yet run.
- Trace: symbol imported only by `scripts/migrate.py` → `named_importers=[scripts/migrate.py]` → dead → `export_not_imported` SATISFIED with a `deletion_cluster` → `_verdict` can reach SAFE / STATIC_CLEAR.
- The docstring promise "an importer we cannot classify counts as REACHABLE" (106-107) does not cover roots, which are classified — wrongly. The module already has `_detect_entry_point` for the target; apply a root heuristic (paths under `scripts/`, `bin/`, `tests/`, `__main__.py`, an `if __name__ == "__main__"` guard) to importer files and count anything not positively dead as live.

**[MEDIUM] `deletion_cluster` override clobbers the do-not-delete action under UNSAFE — CONFIRMED** - `line 496-501`
- Unconditional: with `not_entry_point` REFUTED (verdict UNSAFE) and a dead-importer cluster, `recommended_next_action` becomes "Removable only as a group..." one field below `verdict: unsafe`. Gate on `verdict in (SAFE, STATIC_CLEAR)`.

**[MEDIUM] Text-sweep error payload collapses into SATISFIED — CONFIRMED (downgraded from HIGH: narrow trigger)** - `line 344-346 vs 273`
- Obligation 3 never checks `hits` for `"error"`; `hits.get("results") or []` turns an error dict into "appears only in its own file". `search_text` does return `{"error": ...}` (search_text.py 31-42, 101) but every such path is input validation or repo resolution, which cannot fail here for an already-resolved repo and a symbol-name query — the realistic trigger is the index vanishing between the two calls. The invariant the module states (UNESTABLISHED never collapses into SATISFIED) is still violated by construction. Mirror Obligation 2's guard.
