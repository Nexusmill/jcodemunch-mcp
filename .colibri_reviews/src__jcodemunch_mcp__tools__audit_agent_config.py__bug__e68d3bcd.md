# Colibri review — src/jcodemunch_mcp/tools/audit_agent_config.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\audit_agent_config.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `z-ai/glm-5.3-flash` review, `.colibri_reviews/_external_raw/jcm__audit_agent_config.py__z-ai-glm-5.3-flash.md`)
- sha256: `e68d3bcdfac0a4215dcf0e2af701fd3c70117cd9702eee31c95fcbf4eb98f037` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
Small, real path-normalisation defects; nothing that corrupts state.

## Bugs & vulnerabilities
**[LOW] `lstrip("./")` is a character-class strip — CONFIRMED (impact narrower than reported)** - `line 187, 433`
- What: `"./.cursor/rules/x.mdc".lstrip("./")` → `cursor/rules/x.mdc`. `_FILE_PATH_REF` (113-116) only captures refs beginning `./`, `src/`, `lib/`, ... so the affected shape is `./.dotdir/...`.
- In `_check_dead_paths` the boundary-less `endswith` (189) usually rescues an INDEXED file; a non-indexed on-disk file (`.mdc`, a skipped `.github` yaml) fails the `os.path.exists` fallback (193-195) → false `dead_path`. In `_resolve_section_refs` (433-437) the ref is silently dropped from the concentration math.
- Fix: `if s.startswith("./"): s = s[2:]`.

**[LOW] Suffix match without a separator boundary — CONFIRMED** - `line 189`
- `mysrc/foo.py` satisfies `src/foo.py` (false negative). `_resolve_section_refs` already does it right (436).

**[LOW] `.cursor/rules` directory layout is silently skipped — CONFIRMED** - `line 49, 82`
- `_discover_files` requires `is_file()`; modern Cursor uses a directory of `.mdc` files.

**[LOW] Early return omits keys the normal return carries — CONFIRMED** - `line 634-641 vs 691-712`
- `global_tokens`, `finding_counts`, `skill_advisor` missing on the no-files path.

## Refuted external findings
- LOW "partial index load leaves inconsistent cross-check state": after `store.load_index` returns, the reads at 657-663 are on `CodeIndex` fields that always exist; no realistic exception window between them.
