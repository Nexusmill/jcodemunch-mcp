=== grok_review | grok-4.3 | sha256 18b712cf3be29327 | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\index_folder.py
=== 75s | in=29918 out=8794
==================================================================
**HIGH**  
**Symbol:** `_refresh_git_head_if_advanced` (def at ~line 580) + call sites in `index_folder` fast-path no-change block (~line 820) and mtime-only block (~line 850), plus standard incremental no-change block (~line 1130)  
**Trigger condition:** `incremental=True` + `changed_paths` (watcher) or full incremental path, `_is_branch_delta`/`_fast_is_branch_delta` true (non-base branch), and either (a) no file content changes but `git_head` advanced or (b) mtime-only updates after hash comparison.  
**Impact:** `incremental_save` (base index) is called instead of `save_branch_delta`; branch-specific `git_head`/`file_mtimes` never updated, FreshnessProbe reports stale symbols on the branch index, and branch delta state diverges.  
**Fix:** Extend `_refresh_git_head_if_advanced` (and the mtime-only block) to accept `branch` (or `_current_branch`/`_fast_branch`), then call `save_branch_delta(..., changed_files=[], new_files=[], deleted_files=[], git_head=..., file_mtimes=...)` when branch is set, else the existing `incremental_save`. Update all three call sites to pass the active branch value.

**HIGH**  
**Symbol:** mtime-only early return in watcher fast path (~lines 850-870)  
**Trigger condition:** `changed_paths` supplied, `use_memory_hash_cache` or branch mode, content hashes match (so `actually_changed` empty), `mtime_only_updates` or `_head_advanced` true.  
**Impact:** Always executes `store.incremental_save(...)` (base) even when `_fast_is_branch_delta`; branch index left with stale mtimes/git_head.  
**Fix:** Wrap the `if mtime_only_updates or _head_advanced:` block with the same `if _fast_is_branch_delta: save_branch_delta(...) else: incremental_save(...)` used later in the same function for real changes.

**MEDIUM**  
**Symbol:** `_needs_parser_upgrade(_fast_base_index)` block in fast path (~line 790)  
**Trigger condition:** `use_memory_hash_cache=True` and `_fast_is_branch_delta=True` simultaneously (watcher change set carries hashes on a feature branch).  
**Impact:** The upgrade check forces `existing_index=None` and `use_memory_hash_cache=False` using the *base* index, discarding the already-loaded branch index and forcing a full load later; branch delta path is incorrectly disarmed.  
**Fix:** Change the check to `if _needs_parser_upgrade(existing_index or _fast_base_index):` (or load the correct index for the branch case before the test).

**LOW**  
**Symbol:** `post_discovery_drops` accounting in explicit `paths=` path (~line 1050)  
**Trigger condition:** `paths=[...]` supplied, `incremental=True`, some listed files fail the post-walk language/mtime checks (`_drop("no_language")` etc.).  
**Impact:** `post_discovery_drops` is populated but never passed to `_record_coverage` (only the `paths is None` branch calls it); coverage report for subset refreshes under-reports drops.  
**Fix:** Move the `if paths is None:` guard around the `_record_coverage` call, or always pass `post_discovery_drops` (the coverage helper already accepts it).
