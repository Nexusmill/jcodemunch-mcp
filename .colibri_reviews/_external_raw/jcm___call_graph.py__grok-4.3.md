=== grok_review | grok-4.3 | sha256 02260b6f258df182 | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\_call_graph.py
=== 78s | in=7466 out=9826
==================================================================
**MEDIUM**  
**bfs_callers:280 (initial direct-caller block) and bfs_callees:340 (identical structure)**  
**Trigger:** `max_depth < 1` (including 0) passed to either BFS function.  
**Impact:** Always emits depth-1 results and sets `depth_reached=1`; never returns `([], 0)`.  
**Fix:** Insert `if max_depth < 1: return [], 0` immediately before the depth-1 `for` loop in both functions.

**HIGH**  
**_callers_from_references:140**  
**Trigger:** `_callers_from_references` executes and `index` has no `_symbol_index` attribute (or it is not a dict).  
**Impact:** Unhandled `AttributeError` instead of graceful empty result.  
**Fix:** Replace `caller = index._symbol_index.get(cid)` with `caller = getattr(index, "_symbol_index", {}).get(cid)`.

**MEDIUM**  
**_lsp_callees:225**  
**Trigger:** An LSP edge for a `called_name` that appears more than once in `symbols_by_file[target_file]`.  
**Impact:** `target_line` is read but never used; selection falls back to first list-order match by name only, producing wrong callee entry.  
**Fix:** After `target_line = edge.get("target_line", 0)`, change the inner candidate loop to also require `(target_line and candidate.get("line", 0) == target_line) or candidate.get("name") == called_name`, then keep the `break`.
