=== grok_review | grok-4.3 | sha256 33efde9ed40a6fa9 | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\cli\init.py
=== 69s | in=19926 out=7610
==================================================================
**HIGH**  
**Symbol:** `_read_json` (lines ~140-145)  
**Trigger condition:** Existing JSON config file (claude_desktop_config.json, mcp.json, settings.json, etc.) contains invalid JSON (not just absent).  
**Impact:** Returns {}, so `_patch_mcp_config`, `_merge_hooks` (install_hooks/install_enforcement_hooks), `_unpatch_mcp_config`, and install_status treat the file as empty and overwrite it, losing all other mcpServers/hooks/env entries.  
**Fix:** Change except to only catch OSError for missing file (return {}); on JSONDecodeError raise or return a sentinel that prevents overwrite.

**LOW**  
**Symbol:** `_strip_policy_blocks` (lines ~680-695, the `before` / `new_text` construction)  
**Trigger condition:** `_POLICY_HEADINGS` block starts at offset 0 and non-policy content follows the matched region.  
**Impact:** Produces leading `\n` in the returned text (file begins with blank line after uninstall).  
**Fix:** Replace the before/new_text lines with:  
```python
before = "".join(lines[:start]).rstrip("\n")
if after.strip():
    sep = "\n" if before else ""
    new_text = before + sep + after.lstrip("\n")
else:
    new_text = before + "\n" if before else ""
```
