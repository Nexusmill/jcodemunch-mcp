=== grok_review | grok-4.3 | sha256 9ae704670302279a | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\index_repo.py
=== 63s | in=6676 out=8108
==================================================================
**Finding 1**  
Severity: HIGH  
Line/symbol: `fetch_with_limit` (approx. lines 280-285): `except Exception: return path, ""` (inside `async with semaphore`)  
Trigger condition: Any exception from `fetch_file_content` (httpx errors, 4xx/5xx on a file, network failure, timeout, etc.) for a path in `files_to_fetch`.  
Impact: File is dropped from `current_files`/`raw_files_subset` with no logging or result entry; full index omits the file entirely, incremental treats it as updated but provides no content (inconsistent DB state); caller sees only success or reduced counts.  
Concrete fix: Replace bare `except Exception` with specific handling that logs `path` + `str(e)`, collects failed paths, and either adds a warning to the final result or aborts the run when `len(failed) > 0`.

**Finding 2**  
Severity: MEDIUM  
Line/symbol: `index_repo` incremental block (after line ~320): `files_to_parse = set(changed) | set(new)` then `raw_files_subset = {p: current_files[p] for p in files_to_parse if p in current_files}` passed to `parse_and_prepare_incremental` + `incremental_save(..., changed
