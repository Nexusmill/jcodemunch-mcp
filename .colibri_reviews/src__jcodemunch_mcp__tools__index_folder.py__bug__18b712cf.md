# Colibri review — src/jcodemunch_mcp/tools/index_folder.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\index_folder.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `grok-4.3` review, `.colibri_reviews/_external_raw/jcm__index_folder.py__grok-4.3.md`)
- sha256: `18b712cf3be2932748c3738c540f87e8bacbd7bdbad3b79f1581d75dc05cd5fa` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
One real branch-mode defect, worse than the external review described: no-change runs on a feature branch write the branch HEAD into the BASE index.

## Bugs & vulnerabilities
**[HIGH] No-change paths write to the base index regardless of branch — CONFIRMED** - `line 958-991 (called 1870, 2451), 1948-1954`
- What: `_refresh_git_head_if_advanced` and the mtime-only block call `store.incremental_save` unconditionally, while the real-change paths correctly switch on `_fast_is_branch_delta` / `_is_branch_delta` (1994-2025, 2536-2569).
- Trigger: watcher or manual incremental run on a non-base branch with no indexable content change (a commit touching only non-indexed files, or mtime-only drift).
- Impact: the BRANCH's HEAD (and branch-file mtimes) is stamped into the base index meta. The base is now "at" a commit it was never indexed at; `load_index` then warns the delta is stale (`base_head != index.git_head`, 1589-1596) on every branch load, and the branch delta's own `git_head` never advances so `FreshnessProbe` keeps flagging the branch stale — the exact symptom #330 tried to remove.
- Fix: thread the active branch into `_refresh_git_head_if_advanced` and the mtime-only block; when set, call `save_branch_delta(..., changed_files=[], new_files=[], deleted_files=[], git_head=..., file_mtimes=...)`.

## Refuted external findings
- MEDIUM `_needs_parser_upgrade(_fast_base_index)` (1797) "disarms the branch delta path": the full path it falls to is itself branch-aware (2248-2266) and re-checks the upgrade on the composed index (2281). Cost is one extra load, not a correctness loss.
- LOW `post_discovery_drops` not recorded when `paths=` is given: deliberate (2575-2577, 2912-2914) — a subset refresh must not overwrite the whole-corpus coverage contract.
