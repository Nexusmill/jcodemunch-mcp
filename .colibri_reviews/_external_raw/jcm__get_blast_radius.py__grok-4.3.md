=== grok_review | grok-4.3 | sha256 0fa9bc127c6b8699 | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\get_blast_radius.py
=== 89s | in=7663 out=9744
==================================================================
**MEDIUM**  
**Line/symbol:** `except Exception:` (in `_attach_scip_to_blast`, after `scip_meta_and_stale` / the two `conn.execute` blocks)  
**Trigger condition:** Any exception during `scip_meta_and_stale`, parameterized query execution, `fetchall`, dict construction, or the `confirmed`/`_meta` updates.  
**Impact:** Silent failure — function returns the original result with no SCIP data attached and no error or log emitted to the caller.  
**Fix:** Replace the bare `except Exception:` with `except (sqlite3.Error, KeyError, TypeError, ValueError):` (or the minimal set that can actually occur) and either re-raise or log at warning level before returning `result`.

**MEDIUM**  
**Line/symbol:** `_db_path_str = str(store._sqlite._db_path(owner, name))`  
**Trigger condition:** Every call to `get_blast_radius` (reached unconditionally after result construction).  
**Impact:** Wrong API usage — direct access to private `IndexStore._sqlite` and its `_db_path` method; will break on any internal storage change and can raise `AttributeError` at runtime.  
**Fix:** Add a public method on `IndexStore` (e.g. `get_sqlite_path(owner, name)`) and call that instead; do not reference `_sqlite` or `_db_path` from tool code.

**LOW**  
**Line/symbol:** `except Exception:` (inside the `if cross_repo:` block, around the `list_repos` / `load_index` / `extract_root_package_from_specifier` loop)  
**Trigger condition:** Any failure while enumerating other repos, loading their indexes, or processing their import specifiers.  
**Impact:** Cross-repo results are silently dropped (only a debug log is emitted); caller receives incomplete result with no indication of the failure.  
**Fix:** Narrow to specific exceptions that are expected (e.g. `KeyError`, `AttributeError`, `sqlite3.Error`) or remove the catch so errors surface; at minimum log at `warning` level.
