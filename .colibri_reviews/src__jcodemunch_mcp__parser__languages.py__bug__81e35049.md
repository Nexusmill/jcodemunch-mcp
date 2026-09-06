# Colibri review — src/jcodemunch_mcp/parser/languages.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\parser\languages.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `z-ai/glm-5.3-flash` review, `.colibri_reviews/_external_raw/jcm__languages.py__z-ai-glm-5.3-flash.md`)
- sha256: `81e350492e5ef1559eee385bebf8497cd02f0f709449f36c2097fc42a9b52996` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
All LOW; one external fix was itself wrong and is corrected here from a grammar probe.

## Bugs & vulnerabilities
**[LOW] `HASKELL_SPEC` names a node that does not exist — CONFIRMED, fix corrected** - `line 1301, 1312`
- `type_synon` matches nothing. Probe on the vendored grammar (`tree_sitter_language_pack`, `.venv`): `type Foo = Int` parses to a node named `type_synomym` — the grammar's own misspelling — NOT `type_synonym` as the external review asserted. Use `type_synomym` and pin the grammar version the name depends on; a test that parses one synonym would have caught both the original and the proposed fix.

**[LOW] Dot-less `extra_extensions` keys are silently inert — CONFIRMED** - `line 2156-2163`
- Stored verbatim; every lookup compares dot-prefixed extensions. Normalise or warn.

**[LOW] Extension collisions with no disambiguation — CONFIRMED** - `line 89, 98, 164, 177`
- `.v` (Coq), `.pl` (Prolog), `.pp` (Puppet), `.cl` (OpenCL) route to the wrong parser silently; `.m` has a heuristic (148, 2222), these have neither a heuristic nor a comment.

**[LOW] Ansible basename heuristic fires on generic filenames — CONFIRMED** - `line 2109-2111, 2124-2125`
- `site.yml` / `requirements.yml` are classed Ansible before any path-context check.
