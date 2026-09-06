# Colibri review — src/jcodemunch_mcp/watcher.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\watcher.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `grok-4.3` review, `.colibri_reviews/_external_raw/jcm__watcher.py__grok-4.3.md`)
- sha256: `4f4e844096a34e42bbea3958c118432f8b4b57be93315f32caacee6ca2124ac1` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
Mostly clean: the crash paths the external review flagged are caught one level up by WatcherManager; one unguarded `relative_to` remains plausible.

## Bugs & vulnerabilities
**[LOW] `relative_to` outside the try can crash-loop the watch task — PLAUSIBLE** - `line 408-416, 448, 458`
- What: the `relevant` listcomp runs before the `try` (431-510); a non-descendant event path raises `ValueError` out of `_watch_single`.
- Why unverified: callers always pass a resolved folder (682, 731, 969), so the trigger needs watchfiles to hand back a path with a different prefix (symlinked prefix, 8.3/case variance). No reproduction attempted.
- Bounded impact: `WatcherManager.run` (863-904) records the crash and restarts the task (non-fatal), so it becomes a crash-loop on that event batch; the `watch_claude_worktrees` path (1307) has no manager and would lose the task. Guard with `is_relative_to` → skip.

## Refuted external findings
- MEDIUM "exception from `awatch` escapes uncaught, crashing the task without recording failure": for manager-run tasks it IS recorded (`_record_task_crash`) and restarted (880-904). Residual only on the worktrees path above.
- LOW "`IndexStore` instances leak SQLite handles": `IndexStore` opens and closes a connection per operation; `close()` (index_store.py:399) is a WAL-checkpoint helper, not a handle release. Nothing leaks.
