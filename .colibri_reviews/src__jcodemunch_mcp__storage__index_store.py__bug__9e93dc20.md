# Colibri review — src/jcodemunch_mcp/storage/index_store.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\storage\index_store.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `z-ai/glm-5.3-flash` review, `.colibri_reviews/_external_raw/jcm__index_store.py__z-ai-glm-5.3-flash.md`)
- sha256: `9e93dc206571a106a77af435a8b26e694cc873b1eec5324017910ce89b10caaa` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
No live data-loss path found; a set of contract mismatches, one of which (slug parsing) misidentifies hyphenated owners on the recovery paths.

## Bugs & vulnerabilities
**[LOW] `get_symbol` returns the live dict, contradicting its docstring — CONFIRMED (contract)** - `line 263-274`
- Only symbols carrying BM25 keys get a copy; clean symbols are aliased into `_symbol_index`. No mutating caller traced, so latent. Always copy or document read-only.

**[LOW] Slug → (owner, name) is lossy for hyphenated owners — CONFIRMED** - `line 959-960, 1030-1033`
- `phantom-man-jcodemunch-mcp.db` → `phantom` / `man-jcodemunch-mcp`. Reached only on the corrupted-DB fallback (wrong repo id surfaced in `list_repos`) and the legacy-JSON eager migration (wrong identity persisted by `migrate_from_json`). Derive identity from the payload's `repo` field, never from the slug.

**[LOW] `_safe_repo_component` collisions — CONFIRMED** - `line 441-442`
- `my org` and `my-org` share one slug → silent index sharing.

**[LOW] `_load_index_json_cached` memoizes transient failures — CONFIRMED** - `line 113-122, 687-688`
- `None` is cached under `lru_cache` until the mtime changes; `inspect_index` also does `exists()` then `stat()` with a delete window between them.

**[LOW] `CodeIndex.search` returns raw dicts with BM25 keys — PLAUSIBLE** - `line 314, 326`
- jCodemunch found no `index.search(` caller but reported the absence as not citable (server.py exceeds the corpus size cap), so whether any live path serialises the result is unverified.

## Notes
- `_index_to_dict` (1122-1144) has no caller in `src/`; the external field-gap finding is moot until the method is deleted or used. Recommend deletion.
