# Colibri review — src/jcodemunch_mcp/tools/_call_graph.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\_call_graph.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `grok-4.3` review, `.colibri_reviews/_external_raw/jcm___call_graph.py__grok-4.3.md`)
- sha256: `02260b6f258df182c343009091bd2f1736f1f270d8d65698e1a0f62713bf33c6` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
Clean apart from one resolution imprecision; both external claims about crashes/unreachable guards are refuted from call sites.

## Bugs & vulnerabilities
**[LOW] `_lsp_callees` ignores `target_line` — CONFIRMED** - `line 358, 362-376`
- Read and never used; the match is by name only, first wins, so same-name symbols in one target file (overloads, nested defs) resolve to the wrong callee.

## Refuted external findings
- HIGH `index._symbol_index` may be missing (199): `CodeIndex.__post_init__` always builds it (index_store.py:217).
- MEDIUM `max_depth < 1` returns depth-1 results: unreachable — `get_call_hierarchy` clamps `max(1, min(depth, 5))` (get_call_hierarchy.py:125) and `get_blast_radius` calls only when `call_depth > 0` (get_blast_radius.py:564-568).
