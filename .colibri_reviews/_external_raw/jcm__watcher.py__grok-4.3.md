=== grok_review | grok-4.3 | sha256 4f4e844096a34e42 | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\watcher.py
=== 76s | in=13107 out=7655
==================================================================
**Finding 1**  
Severity: MEDIUM  
Symbol: `Path(path).relative_to(folder_path)` (and identical call for `cached_rel`) inside `_watch_single` (the listcomp for `relevant` and the subsequent `for ct, p in relevant` loop)  
Trigger condition: `awatch` yields a `(change_type, path)` where `path` is not a descendant of `folder_path` (occurs with `follow_symlinks=True`, symlinked entries, or certain WSL/inotify events).  
Impact: `ValueError` propagates out of the listcomp (outside the inner `try`) or the loop, terminating the watch task with no `mark_reindex_failed` or cleanup.  
Fix: Replace both `relative_to` sites with `if not Path(path).is_relative_to(folder_path): continue` (or `try: rel = Path(path).relative_to(folder_path) except ValueError: continue`).

**Finding 2**  
Severity: MEDIUM  
Symbol: `async for changes in awatch(...)` (the top-level iteration in `_watch_single`, after the import)  
Trigger condition: `awatch` raises (directory becomes inaccessible, permission change, internal watchfiles error, or cancellation during iteration).  
Impact: Exception escapes `_watch_single` uncaught (no surrounding `try` for the generator), crashing the task without recording failure or releasing resources.  
Fix: Wrap the `async for` (and the `relevant` computation) in `try: ... except Exception as e: logger.exception(...); mark_reindex_failed(repo_id, str(e)); break`.

**Finding 3**  
Severity: LOW  
Symbol: `store = IndexStore(base_path=storage_path)` (in `_watch_single`, `_do_reindex`, `_stop_watching`, and the `use_repos` path in `watch_claude_worktrees`) with no subsequent `close()`  
Trigger condition: Any call to `ensure_indexed`, worktree removal, or per-folder watch startup (short-lived `store` instances).  
Impact: SQLite connections/cursors remain open; repeated calls accumulate handles.  
Fix: Add `store.close()` immediately after the last use of each short-lived `store` (or make `IndexStore` a context manager and use `with`).
