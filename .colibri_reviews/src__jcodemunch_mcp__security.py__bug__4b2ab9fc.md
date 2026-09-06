# Colibri review — src/jcodemunch_mcp/security.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\security.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `grok-4.6` review, `.colibri_reviews/_external_raw/jcm__security.py__grok-4.6.md`)
- sha256: `4b2ab9fc5c726324da81228316f93ff8ebde42d4d2bd821fe2a3e7d9fc84c464` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
Two of the external MEDIUMs target a function nothing calls; the live defect is project overrides being ignored for two config keys.

## Bugs & vulnerabilities
**[MEDIUM] Project-level `exclude_secret_patterns` / `exclude_skip_directories` are inert — CONFIRMED** - `line 148, 260`
- What: `is_secret_file` and `_excluded_skip_directories` call `_config.get` without `repo`, and their signatures carry none, so the project overlay never applies (same class as #300/#390/#391). Callers: index_folder 579/1105, index_file 141, index_repo 256; `get_skip_directories` ← index_folder 217.
- Refuted half: "a string value iterates characters" — `CONFIG_TYPES` requires `list` (config.py 512-513) and `_validate_type` rejects a string at load time in both loaders.
- Fix: add `repo: Optional[str] = None` to `is_secret_file`, `_excluded_skip_directories`, `get_skip_directories`, `get_skip_patterns` and pass it from the walkers.

**[LOW] `.min.js.map` / `.min.css.map` can never match — CONFIRMED** - `line 303, 316-317`
- `os.path.splitext` yields `.map`.

**[LOW] `get_skip_directories` cannot un-skip the glob entries — CONFIRMED** - `line 203-205, 264-269 vs 272-278`
- `SKIP_DIRECTORIES` stores `[^/]*\.xcodeproj`, so a user `*.xcodeproj` exclusion never matches on the index_folder path while `get_skip_patterns` honours it on the index_repo path.

## Refuted external findings
- MEDIUM `should_exclude_file` `relative_to` on an unresolved path, and LOW extension-only binary check inside it: `should_exclude_file` (572-623) has NO caller in `src/` (jCodemunch: definition only). The live gate `_should_index_file` resolves paths (index_folder 522) and content-sniffs binaries (601). Recommend deleting the dead function rather than fixing it.
