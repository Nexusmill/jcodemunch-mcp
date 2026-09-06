=== grok_review | grok-4.3 | sha256 0b7ee24fa316fe5b | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\plan_refactoring.py
=== 119s | in=26048 out=10541
==================================================================
**HIGH**  
**exact line/symbol:** `plan_refactoring:80` (`owner, name = repo.split("/", 1)`)  
**trigger condition:** `repo` lacks exactly one `/` (e.g. `"owner"`, `"owner/repo/extra"`, or empty)  
**impact:** `ValueError` (unpack) propagates uncaught; callers receive exception instead of `{"error": ...}` dict.  
**fix:**  
```python
if "/" not in repo:
    return {"error": f"repo must be in owner/name form: {repo}"}
owner, name = repo.split("/", 1)
```

**HIGH**  
**exact line/symbol:** `_extract_ts_overload_signatures:620` (the `while current_idx < len(lines)` loop and its `if re.match(r"^\s*(export\s+)?function\s+" + re.escape(sym_name) + r"\s*\(" , next_line)`)  
**trigger condition:** TypeScript overload signatures (ending `:`) immediately followed by the real definition line (containing `{` or body)  
**impact:** `old_def` includes the implementation line; `definition_edit` replaces real body start, corrupting the file.  
**fix:** Change collection condition to also require the line (after strip) ends with `:` and contains no `{` (or reuse `_TS_OVERLOAD_PATTERN` adapted for `sym_name`).

**MEDIUM**  
**exact line/symbol:** `_ensure_unique_context_smart:480` (the `while content.count(old_text) > 1 and (above + below) < max_expand` loop)  
**trigger condition:** symbol occurs >1 time and duplicate blocks are >5 lines apart (or identical within expand budget)  
**impact:** returned `old_text` still occurs >1 time in `content`; generated plan contains ambiguous edit blocks that may apply to wrong site or fail.  
**fix:** After the loop, if `content.count(old_text) > 1` then either return an error dict or fall back to full-line context with a warning.
