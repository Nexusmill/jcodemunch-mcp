=== grok_review | grok-4.3 | sha256 133e72bbbe7dd20e | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\storage\token_tracker.py
=== 59s | in=16119 out=6621
==================================================================
**HIGH**: `_ensure_loaded` (lines 140-142: `if self._loaded: return` then unconditional `self._base_path = base_path` only on first load) + callers `add`/`get_total`/`session_stats`/`_flush_locked` (which always use `self._base_path`).  
Trigger: first `record_savings`/`add`/`record_encoding_savings` etc. passes `base_path=None` (or one value); later call passes a different `base_path`.  
Impact: all subsequent totals, unflushed deltas, daily rollups, and `_savings.json` writes go to the first path only; cross-store mixing or loss of per-store savings.  
Fix: remove the early return or make `_loaded` + `_base_path` per-path (e.g. dict keyed by resolved path, reload when base_path differs).

**MEDIUM**: `_ensure_perf_db_locked` (line ~340: `if self._perf_db_failed: return None` at entry) + the assignment inside the connect `except` (only when `base_path is None`).  
Trigger: any default-path (`base_path=None`) connect failure sets the flag; subsequent explicit-`base_path` calls still hit the early return.  
Impact: `perf_telemetry_enabled` permanently disabled for every store after one default failure.  
Fix: delete the early `if self._perf_db_failed` guard (or replace with a per-default flag only); keep the `if base_path is None: self._perf_db_failed=True` assignment.

**MEDIUM**: `_runtime_signal_summary` inner `try` (around lines 780-800: `conn = connect_readonly(...)` ... `conn.close()` only on the `if row is None` and normal paths; `except _sqlite3.Error:` has no `finally` or close).  
Trigger: `sqlite3.Error` (or any exception) after successful `connect_readonly` but before a `close()` call.  
Impact: SQLite connection handle leaked until GC/process exit.  
Fix: change the inner block to `conn = connect_readonly(...); try: ... finally: conn.close()` (or equivalent).

**LOW**: `write_pulse` (lines ~615-620: `root = Path(base_path) if ... else ...; pulse_path = root / _PULSE_FILE` then `tmp.write_text` with no `mkdir`).  
Trigger: `JCODEMUNCH_EVENT_LOG=1` and target directory does not yet exist.  
Impact: write fails, exception swallowed at DEBUG, pulse never created.  
Fix: insert `root.mkdir(parents=True, exist_ok=True)` immediately after computing `root`.
