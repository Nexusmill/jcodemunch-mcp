# Colibri review — src/jcodemunch_mcp/storage/sqlite_store.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\storage\sqlite_store.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `grok-4.6` review, `.colibri_reviews/_external_raw/jcm__sqlite_store.py__grok-4.6.md`)
- sha256: `811ec1b7db80b55f20eeb0e354a62b1f060e798777d69982f1b025969d784b49` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
Not safe for concurrent multi-process use as-is: a cold `load_index` overlapping a writer can cache a torn index as fresh. Everything else is bounded.

## Bugs & vulnerabilities
**[HIGH] `load_index` reads three generations and caches the torn result under the new mtime — CONFIRMED** - `line 1547, 1560-1561, 1601-1604`
- What: `_read_meta`, `SELECT * FROM symbols`, `SELECT * FROM files` run as three autocommit statements (connection opened `isolation_level=None`, line 809) with no `BEGIN`; `open_selective` (line 1667) already wraps its reads in a read transaction "so the meta, files and symbols rows all describe the same generation".
- Trigger: a writer commits between the statements. Writers (`_incremental_save_locked` 1944, `_save_branch_delta_locked` 997, `save_index` 3322) take the indexwrite lock only, never `_load_lock_for`, and the watcher process writes while a tool process performs its documented minutes-long cold load.
- Impact: meta/symbols/files from different generations are assembled into one `CodeIndex`; the post-load re-stat (1601) then stores it under the post-write mtime (1604), so every later `load_index` treats the torn object as current until the next write.
- Fix: `conn.execute("BEGIN")` before `_read_meta`, `ROLLBACK` after the two SELECTs; stat before the read and after the commit, and skip `_cache_put` when the mtime moved.

**[MEDIUM] Unchunked `IN (...)` lists in the write paths — CONFIRMED** - `line 1949-1950, 1955-1958, 1965-1966` (and `_save_branch_delta_locked` ~999)
- What: `",".join("?" * len(files_to_remove))` with no chunking, while `_SELECT_CHUNK = 900` (line 1611) exists precisely because `SQLITE_MAX_VARIABLE_NUMBER` is 999 on older builds and 32766 on modern ones.
- Trigger: one delta with more changed/new/deleted paths than the bound (mass reformat, branch switch on a 16k-file tree on an old-sqlite Python).
- Impact: `OperationalError: too many SQL variables`; the transaction rolls back and the watcher reindex fails.
- Fix: loop the lists in `_SELECT_CHUNK` slices as `open_selective` does.

**[MEDIUM] File-row `INSERT OR REPLACE` takes metadata only from caller kwargs — PLAUSIBLE (API hazard, no live trigger)** - `line 1953-1961, 1988-2001, 2967`
- What: `preserved` carries only hash+mtime, so language/summary/blob_sha/imports become `""`/`[]` for any changed file whose caller omits that kwarg; in memory `_patch_dict(old.file_hashes, None, files_to_remove)` strips changed files' hashes while the DB keeps the preserved hash.
- Why unverified: every in-repo caller with non-empty `changed_files` passes the metadata (index_folder 2011-2025, 2555-2569; index_repo 572-582) and every metadata-only caller passes `changed_files=[]` (958-991, 1639-1644, 1948-1954). index_repo passes no `file_hashes`, so its in-memory hashes diverge from the DB, but GitHub repos diff by blob sha (index_repo 463-468), so nothing reads them.
- Fix: SELECT the full row into `preserved` and fall back per column.

**[LOW] Empty-hash rows are classed "new" but their old symbols are never deleted — PLAUSIBLE** - `line 2183, 2249, 1947`
- What: `old_hashes` excludes empty-hash rows, so such a path is "new"; `_incremental_save_locked` deletes symbols only for changed|deleted, and `INSERT OR REPLACE` by id leaves rows with different ids in place.
- Why unverified: index_folder always supplies `file_hashes`; index_repo writes `""` for new files but diffs by blob sha thereafter and only falls back to `store.detect_changes` when `file_blob_shas` is empty (index_repo 463, 536). No end-to-end sequence producing the duplicate was traced.
- Fix: treat empty-hash-but-present paths as changed so their symbols are removed first.

**[LOW] `_initialized_dbs` first-connect race + connection leak on migration failure — PLAUSIBLE** - `line 809, 815-849`
- What: check-then-add on a class-level set with no lock; two threads first-touching a pre-v17 DB both run the migration chain (830-847) and the second hits "duplicate column" on an ALTER; the connection from 809 is not closed on that throw.
- Why unverified: needs a concurrent first open of a stale-version DB inside one process (watcher task + tool call). Fix: per-`db_key` lock around the init block; close the connection on failure.

## Missing safeguards
- No shared read-transaction helper for the load paths (only `open_selective` has one).
- No shared chunking helper for `IN` lists on the write side.
