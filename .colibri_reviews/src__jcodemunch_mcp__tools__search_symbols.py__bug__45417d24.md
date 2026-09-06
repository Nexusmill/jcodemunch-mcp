# Colibri review — src/jcodemunch_mcp/tools/search_symbols.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\search_symbols.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `z-ai/glm-5.3-flash` review, `.colibri_reviews/_external_raw/jcm__search_symbols.py__z-ai-glm-5.3-flash.md`)
- sha256: `45417d243830df210beb19100a7bdfcf1ddf9a4af9f4bae189b1939fec917f9a` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
The lexical path can silently drop the best identity matches for common queries; the rest is contract polish.

## Bugs & vulnerabilities
**[HIGH] Inverted-index narrowing drops identity-channel matches — CONFIRMED** - `line 966-974, 367, 990`
- What: candidates are the union of posting lists for full query tokens; the full scan runs only when NO posting matches. `_identity_score` (prefix / segment / qualified-id, line 367) is evaluated inside `_bm25_score` (990) and therefore never runs for a symbol excluded by the narrowing.
- Trace: query `foo`; index holds `foo_helper` (tokens foo, helper) and `foobar` (token foobar). `inverted["foo"]` is non-empty so `foobar` is never scored although identity would give it the top tier. Fuzzy cannot rescue it (edit distance 3 > default 2, trigram Jaccard 0.25 < 0.4). Same for `storage.indexstore` vs `IndexStore`.
- Impact: recall loss with no signal, worst exactly when the query is a common token.
- Fix: after narrowing, union in every symbol whose lowercased name starts with any raw query token or whose id contains the joined query (one cheap pass), or skip narrowing for identifier-shaped single-token queries.

**[MEDIUM] Fuzzy pass appends after budget packing — CONFIRMED** - `line 1056-1065, 1068-1138, 1075`
- Packing runs first; the fuzzy loop then appends up to `max_results` rows with no budget charge, and `existing_ids` is built from the PACKED list so exact matches the packer dropped re-enter labelled `fuzzy`. `meta.tokens_used` reports the overshoot honestly (1173-1177) but the contract is violated.
- Fix: collect fuzzy candidates before packing and pack the combined list once.

**[LOW] Bounded-heap ties resolve by insertion order — CONFIRMED** - `line 1036`
- Strict `>` on `heapreplace`; equal scores (centrality 0.0, identity ties) rank by SQLite row order. Same class the semantic path fixed in #398/#403.

**[LOW] Fuzzy rows echo the signature-fallback summary — CONFIRMED** - `line 1125 vs 1023`
- Use `_row_summary(sym)` on the fuzzy path too (jcm#328 regression on one path).
