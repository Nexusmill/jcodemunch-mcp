# Colibri review — src/jcodemunch_mcp/parser/imports.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\parser\imports.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `grok-4.3` review, `.colibri_reviews/_external_raw/jcm__imports.py__grok-4.3.md`)
- sha256: `a677573267817dcf68a5188bc303759f9bd7845d0d44500cbe7473e0b5edecfa` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
One confirmed data-loss defect in the Rust import extractor.

## Bugs & vulnerabilities
**[MEDIUM] `_extract_rust_imports` keeps one `use` per crate — CONFIRMED** - `line 316-328`
- What: `seen` is keyed on the first `::` segment (319-321), so `use std::fs; use std::io;` records only `std::fs`; every later `use` from the same crate is dropped. The specifier recorded is the full path of the first one, not the "first path segment" the comment (318) claims.
- Impact: the Rust import graph is incomplete for essentially every real file — `find_importers`, blast radius and centrality all under-count.
- Fix: compute `spec = raw.split("{")[0].rstrip(":").strip()` once, dedup on `spec`, append under `spec`.
