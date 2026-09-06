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

## Fixed 2026-09-06 (remediation item 6, TDD, gated commit)
- **HIGH inverted-index narrowing drops identity matches - FIXED.** After the posting-list
  union (and only when it is non-empty, so the no-posting full-scan fallback is untouched) one
  pass over `index.symbols` adds every symbol whose lowercased name starts with, or whose lowercased id contains,
  either probe `_identity_score` itself uses (the raw query, the joined token string; never
  individual stemmed tokens - my first cut used those and would have over-widened) so
  `_bm25_score` can score them. Test:
  `tests/test_search_symbols_identity_union.py` - query `foo` over `foo_helper` / `Foobar` /
  `foobaz_loader` / `unrelated`: RED on the old bytes (`['foo_helper']` only), GREEN now; the
  `foobar`-exact ranking test passed before too (pin). Cost: one string pass per query when
  narrowing engages; the BM25 scoring pass, not this, is the expensive part.
- **Surfaced by the union and fixed in the same commit - packer under-charged every row.**
  With more candidates the full suite's `test_v1_108_55::test_compact_payload_tracks_budget`
  went red (929B delivered vs 800B budget, 6 rows): `_packing_cost_bytes` measured the row
  BEFORE the FreshnessProbe stamped `_freshness` on every packed row (retrieval/freshness.py
  `annotate`, at the exit), so the packer admitted one row too many whenever the corpus offered
  enough candidates - the old 5-candidate corpus hid it. First cut (reserve the widest bucket
  in the cost) broke the sibling contract `tokens_used <= payload // 4` (over-charge) and was
  reverted; the root fix is ordering: the lexical exit now builds the probe and stamps the heap
  rows BEFORE packing, so the packer charges the delivered row and `tokens_used == payload //
  4`; the exit's second `annotate()` stamps the fuzzy rows appended after packing. Test:
  `test_packed_rows_are_charged_with_their_freshness_stamp` (10-name corpus, budget 200).
  Open: the fusion and semantic exits still stamp after packing (same defect class, not
  exercised by this item - recorded here, LOW); `_runtime_confidence` is stamped post-packing
  on all exits when runtime traces exist.
- The MEDIUM (fuzzy pass appends after budget packing) and the two LOWs are still open.
