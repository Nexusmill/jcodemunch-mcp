# Colibri review — src/jcodemunch_mcp/cli/init.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\cli\init.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `grok-4.3` review, `.colibri_reviews/_external_raw/jcm__init.py__grok-4.3.md`)
- sha256: `33efde9ed40a6fa9babf62fd7abe9fe9e5403b370b88c36548758f08c40c95a1` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
One real data-loss-shaped defect (recoverable via the .bak) and a cosmetic one.

## Bugs & vulnerabilities
**[MEDIUM] Invalid JSON is treated as an empty config and overwritten — CONFIRMED (downgraded from HIGH: `.bak` is written)** - `line 306-313, 331-347, 316-322`
- What: `_read_json` returns `{}` on `JSONDecodeError`, so `_patch_mcp_config` rewrites a syntactically broken but recoverable client config (a trailing comma in `claude_desktop_config.json`) as `{"mcpServers": {"jcodemunch": ...}}` and prints "added jcodemunch"; `_merge_hooks` and the status readers see the same empty dict.
- `_write_json` copies a `.bak` first when `backup=True` (the default), which is why this is MEDIUM: the user's other servers/hooks vanish from the LIVE file silently but can be restored by hand.
- Fix: distinguish missing (→ `{}`) from invalid (→ refuse with the parse error and the path).

**[LOW] `_strip_policy_blocks` emits a leading newline when the region starts at offset 0 — CONFIRMED** - `line 1532-1534`
