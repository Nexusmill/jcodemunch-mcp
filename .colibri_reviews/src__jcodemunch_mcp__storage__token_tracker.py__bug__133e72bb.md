# Colibri review — src/jcodemunch_mcp/storage/token_tracker.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\storage\token_tracker.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `grok-4.3` review, `.colibri_reviews/_external_raw/jcm__token_tracker.py__grok-4.3.md`)
- sha256: `133e72bbbe7dd20e9927596cffeb42da3dfd9eb2295fcec409f1b18d2482883a` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
Telemetry-only module; one real path-binding defect with a live mixed caller, the rest small.

## Bugs & vulnerabilities
**[MEDIUM] `_ensure_loaded` binds the savings path on the first call only — CONFIRMED (downgraded from HIGH: telemetry data)** - `line 164-178, 1008`
- What: `if self._loaded: return` precedes `self._base_path = base_path`, and `_flush_locked` always writes `_savings_path(self._base_path)`.
- Trigger is live: `winnow_symbols` passes `base_path=storage_path` (winnow_symbols.py:326) while every other tool passes none, so whichever runs first decides where ALL savings for the process are persisted (custom storage vs `~/.code-index`).
- Fix: key `_loaded`/totals per resolved path, or reload when the path differs.

**[LOW] `_perf_db_failed` gates every path, contradicting its own docstring — CONFIRMED** - `line 721-725, 808-809`
- The flag is SET only for the default path (as documented) but CHECKED for all paths, so one default-path failure disables telemetry for explicit-path stores too.

**[LOW] `_runtime_signal_summary` skips `conn.close()` on an sqlite error — CONFIRMED** - `line 1304-1321`
- Transient (CPython closes it at frame exit); use `try/finally`.

**[LOW] `write_pulse` never creates a custom `base_path` root — CONFIRMED** - `line 1233-1247`
- Failure is swallowed at DEBUG. Add `root.mkdir(parents=True, exist_ok=True)`.
