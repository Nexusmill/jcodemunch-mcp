=== grok_review | grok-4.3 | sha256 fb096f7faf5cf656 | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\search_ast.py
=== 61s | in=11147 out=5989
==================================================================
**Finding 1**  
Severity: HIGH  
Location: `_child_statement_count` (lines ~140-148), specifically `text = child.text` and the subsequent `text.strip() not in (b"", ...)`  
Trigger condition: `_detect_empty_catch` invoked on any file containing a catch/except node (any language with `_CATCH_NODES` entries).  
Impact: `AttributeError` (if `.text` absent) or type mismatch / incorrect count (str vs bytes, None) causes the detector to raise, which propagates uncaught from `search_ast` (no try around detector calls).  
Fix: Replace the block with `text = _node_text(child, source_bytes)` and change the comparison tuple to strings: `if text and text.strip() not in ("", "pass", ";"):`.

**Finding 2**  
Severity: HIGH  
Location: `_find_param_reassignments` (line ~310), `lhs = current.children[0]`  
Trigger condition: Any `reassigned_param` run on a function containing an assignment/augmented_assignment node.  
Impact: Wrong (or missing) parameter name extraction because tree-sitter assignment nodes do not guarantee the target is always `children[0]`; can produce incorrect matches or skip valid reassignments. No bounds check on `children`.  
Fix: Replace with proper LHS extraction using the same style as `_extract_simple_call_name` (walk children for identifier/property nodes before the operator) or use node fields if available.

**Finding 3**  
Severity: MEDIUM  
Location: `_detect_bare_except` (Python branch, lines ~175-195)  
Trigger condition: `bare_except` preset on any Python file with `except_clause` nodes.  
Impact: `has_type` is computed but never read; the subsequent `is_bare` logic is independent and contains its own (different) heuristic. Results in incorrect bare-except classification.  
Fix: Remove the unused `has_type = any(...)` block entirely; keep only the `child_types` / `type_found` logic that actually sets `is_bare`.

**Finding 4**  
Severity: MEDIUM  
Location: `search_ast` (line ~455), `for sym in index.symbols:` (and same access inside `_enrich_matches`)  
Trigger condition: `load_index` returns an object without a `.symbols` attribute (stale index, partial load, or store change).  
Impact: Unhandled `AttributeError` instead of graceful error. Contradicts the defensive `getattr` used for `source_root` and `file_languages` two lines above.  
Fix: Change to `getattr(index, "symbols", [])` (or raise a clear error if absent).

**Finding 5**  
Severity: LOW  
Location: `search_ast` (lines ~475-476 and ~480-481)  
Trigger condition: `get_parser(ts_lang)` fails or `parser.parse` raises for any file (unsupported language string, parser registration issue, or internal tree-sitter error).  
Impact: File is silently skipped (`except Exception: continue`); no logging, no partial results, and `files_scanned` undercounts without indication.  
Fix: Change to `except Exception as e: logger.debug("parse failed for %s: %s", fpath, e); continue`.
