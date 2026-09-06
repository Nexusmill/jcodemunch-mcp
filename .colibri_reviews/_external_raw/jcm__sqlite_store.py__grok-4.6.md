=== grok_review | grok-4.6 | sha256 811ec1b7db80b55f | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\storage\sqlite_store.py
=== 771s | in=36617 out=25705
==================================================================
## HIGH — `load_index`: torn snapshot + cache poison under concurrent write

**Where:** `SQLiteIndexStore.load_index` — autocommit `SELECT` of meta / symbols / files with no `BEGIN`; then `_cache_put(..., post_mtime_ns, index, branch)` after a re-stat.

**Trigger:** A cold `load_index` (documented 7–11 min on a large repo) overlaps `save_index` / `incremental_save` on the same `.db`. Writers do **not** take `_load_lock_for`; they only take `indexwrite`. Connection is `isolation_level=None`, so each statement is its own snapshot.

**Impact:**
1. Meta, symbol rows, and file rows can come from different generations (partial reindex mixed with old rows).
2. The loader then stats `.db`/`.db-wal` **after** the write and caches that torn/stale `CodeIndex` under the **new** mtime. Later hits treat it as fresh until the next write. `open_selective` already does `BEGIN` for this reason (`Arc 1's consistency guarantee`); the full load path does not.

**Fix:** Wrap the three reads in one `BEGIN`/`COMMIT` (or `BEGIN`/`rollback`) read transaction. Capture `mtime_ns` before the read; after commit, re-stat. If mtime changed, do not `_cache_put` (retry or return uncached). Optionally have writers invalidate via `_cache_evict` rather than only putting the `branch=""` key.

---

## MEDIUM — `incremental_save` / `save_branch_delta`: unchunked `IN (...)` vs `SQLITE_MAX_VARIABLE_NUMBER`

**Where:** `_incremental_save_locked` (`DELETE FROM symbols WHERE file IN`, `SELECT ... files WHERE path IN`, `DELETE FROM files WHERE path IN`); `_save_branch_delta_locked` (`DELETE FROM branch_deltas WHERE branch = ? AND file IN`). Contrast `_SELECT_CHUNK = 900` on `open_selective`, which exists because the limit is 999 on older SQLite and 32766 on modern builds.

**Trigger:** One delta with more changed/new/deleted paths than the bound (branch switch, mass reformat, large checkout).

**Impact:** `sqlite3.OperationalError: too many SQL variables`. Incremental/branch write fails; index left as before the transaction (if `BEGIN` succeeded) or the tool errors mid-watch.

**Fix:** Reuse `_SELECT_CHUNK` and loop the `IN` lists in chunks of 900, same as `open_selective`.

---

## MEDIUM — `_incremental_save_locked`: file row replace drops metadata; patch path drops hashes

**Where:** File `INSERT OR REPLACE` in `_incremental_save_locked` (language / summary / blob_sha / imports taken only from caller kwargs, default `""` / `[]`). `_patch_index_from_delta` → `_patch_dict(old.file_hashes, file_hashes, files_to_remove)` when `file_hashes` is `None`. Comment at the file loop says “fall back to preserved” but `preserved` only has `hash` and `mtime_ns`.

**Trigger:** `incremental_save(..., file_languages=None, file_summaries=None, file_blob_shas=None, imports=None)` (all optional), or `file_hashes=None` while the in-memory cache is warm (patch path).

**Impact:**
- DB: changed files lose language, summary, blob SHA, imports (full-row replace). Language counts then ignore those files (`WHERE language != ''`).
- Memory: changed files are removed from `file_hashes` and not put back, while the DB still keeps the old hash. Cached `CodeIndex` diverges from SQLite until a full reload.

**Fix:** `SELECT path, hash, mtime_ns, language, summary, blob_sha, imports, size_bytes` into `preserved`. For each column, caller value if present else preserved. In `_patch_dict`, when `delta` is `None`, do not strip keys that were only in `files_to_remove` unless you also have replacements; or pass DB-preserved hashes into the patch.

---

## MEDIUM — empty-hash files classified as “new” but old symbols are not deleted

**Where:** `detect_changes_with_mtimes` / `detect_changes_from_hashes` (`old_hashes = {..., if r["hash"]}`); `_incremental_save_locked` only deletes symbols for `deleted_files | changed_files`, not `new_files`.

**Trigger:** A path already in `files` with `hash` NULL/empty (the case the mtime helper documents as “treated as if it does not exist … indistinguishable from a deleted file”), then a later incremental run lists it as new.

**Impact:** Documented intent is delete+re-add. Implementation only INSERTs. Pre-existing symbol rows for that path remain (new ids via `INSERT OR REPLACE` do not remove old ids). Duplicate symbols, stale outlines, wrong search/impact results.

**Fix:** Treat empty-hash paths that still exist on disk as `changed` (or add them to `files_to_remove` before insert), so `DELETE FROM symbols WHERE file IN (...)` runs for them. Align the docstring with that.

---

## MEDIUM — `_initialized_dbs` first-connect race

**Where:** `SQLiteIndexStore._connect` / class set `_initialized_dbs` (no lock). Migrations such as `_migrate_v4_to_v5` (`PRAGMA table_info` then `ALTER TABLE ... ADD COLUMN`).

**Trigger:** Two threads (watcher + tool) open the same not-yet-initialized DB in one process.

**Impact:** Both see “not initialized”, both migrate. Duplicate `ALTER` → `duplicate column name`. First load/save of an old DB can fail spuriously; connection from `_connect` is not closed on that throw (leak until GC).

**Fix:** Guard the init/migration block with a threading lock (or lock per `db_key`). On migration failure, `conn.close()` before re-raising. Catch duplicate-column / already-exists as idempotent.
