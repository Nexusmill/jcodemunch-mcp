# Colibri review — src/jcodemunch_mcp/tools/search_ast.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\search_ast.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `grok-4.3` review, `.colibri_reviews/_external_raw/jcm__search_ast.py__grok-4.3.md`)
- sha256: `fb096f7faf5cf656f2636202b7fc10f425df7eaf2d8b16682c23b9a1016071a8` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
Both external HIGHs are wrong; what remains is a silent skip and one narrow miss.

## Bugs & vulnerabilities
**[LOW] Parser failures are skipped silently — CONFIRMED** - `line 1138-1142`
- `except Exception: continue` with no log; `files_scanned` undercounts with no indication.

**[LOW] Prefix `update_expression` reassignments are missed — CONFIRMED (narrowed from the external HIGH)** - `line 670`
- `children[0]` is the LHS for `assignment` / `augmented_assignment` / `assignment_expression`; for a prefix `++x` it is the operator, so that reassignment is not reported. Not the "wrong name extraction" claimed.

## Refuted external findings
- HIGH `_child_statement_count` uses `child.text` (250-251): py-tree-sitter exposes `Node.text` as bytes for trees parsed from bytes (`parser.parse(source_bytes)`, 1140); the bytes-tuple comparison is type-consistent. No AttributeError path.
- MEDIUM `has_type` "causes incorrect classification": it is computed and never read (314-321) — dead code; `is_bare` is decided solely by the 323-337 walk. Quality note, not a bug.
- MEDIUM `index.symbols` may be absent (957, 1093): a `CodeIndex` always has it.
