=== hy4_review | z-ai/glm-5.3-flash | sha256 45417d243830df21 | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\search_symbols.py
=== 443s | in=22925 out=19411
==================================================================
## Findings

### 1. HIGH — Inverted-index candidate narrowing silently drops identity-channel matches (lexical path)

**Location:** the `candidate_indices` narrowing loop in `search_symbols` (the `for term in query_terms: posting = inverted.get(term)...` block) interacting with `_identity_score` / `_bm25_score`.

**Trigger:** The narrowing keeps only symbols whose token bag contains at least one *full* query token, and the full-scan fallback fires only when **no** posting list matches. Whenever at least one other symbol matches a query term, any symbol whose identity match is prefix- or segment-based — but which shares no full token with the query — is excluded before `_bm25_score` ever runs.

Concrete trace: query `"foo"`, index contains `foo_helper` (tokens `["foo","helper"]`) and `foobar` (tokens `["foobar"]`). `inverted["foo"] = [idx(foo_helper)]`, so `candidate_indices` is non-empty and `foobar` is never scored — even though `_identity_score` would award it 30.0 (name prefix), which would outrank the token-overlap hit. The fuzzy pass does not rescue it: edit distance `foo→foobar` = 3 > default `max_edit_distance=2`, and trigram Jaccard = 1/4 = 0.25 < default `fuzzy_threshold=0.4`. Same failure for the qualified-ID channel (`query_joined in sym_id_lower`, scored 20.0): e.g. query `storage.indexstore` tokenizes to `["storage","indexstore"]`, and `IndexStore`'s tokens (`index`, `store`) match neither posting list.

**Impact:** The exact/prefix identity matches — the highest-scoring tier of the ranking — silently vanish from results precisely when the query is popular enough that other symbols share a token. Recall loss with no error signal.

**Fix:** After building `candidate_indices`, union it with identity matches before scoring — e.g. one cheap pass adding every symbol whose `name.lower()` starts with any raw query token or whose `id.lower()` contains the raw query — or skip narrowing when the raw query is identifier-shaped (single token, no whitespace).

---

### 2. MEDIUM — Fuzzy pass appends results after token-budget packing, bypassing the budget

**Location:** lexical path in `search_symbols`: the `if token_budget is not None:` packing block, followed by the `if run_fuzzy:` block.

**Trigger:** `token_budget` set AND (`fuzzy=True` OR `max_bm25_score < _FUZZY_NEAR_MISS_THRESHOLD`). The packer runs first (`scored_results = packed`), then the fuzzy pass appends up to `max_results` entries with no budget accounting. Additionally, `existing_ids = {e["id"] for e in scored_results}` is built from the *packed* list, so exact BM25 matches that were dropped by the packer re-enter as `match_type="fuzzy"` rows — mislabeled and uncharged.

**Impact:** Response exceeds the caller's `token_budget` by up to `max_results` rows (full-detail rows are the expensive case). `meta["tokens_used"]` honestly reports the overshoot and `tokens_remaining` clamps to 0, but the budget contract itself is violated; `budget_truncated`/`truncated` also don't reflect the fuzzy additions.

**Fix:** Collect fuzzy candidates before packing and pack the combined list once, or charge each fuzzy entry against the remaining budget inside the fuzzy loop.

---

### 3. LOW — Bounded-heap tie-breaking is insertion-order arbitrary (lexical path)

**Location:** the heap maintenance in `search_symbols`: `elif heap_score > heap[0][0]: heapq.heapreplace(...)`.

**Trigger:** Equal `heap_score` values. This is common: for `sort_by="centrality"` every file with PageRank 0 ties at `0.0` (most files in a large repo), and identity-only scores (50/30/20) tie exactly. `heapreplace` fires only on strictly-greater, so among ties whichever symbol `index.symbols` yielded first wins — i.e. SQLite row handback order.

**Impact:** Same defect class the semantic path fixed in v1.108.228 (#398/#403): two installs of the same version can rank tied results differently based on row order. Deterministic per index, but arbitrary and unstable across reindexes.

**Fix:** Break ties on a stable total-order key, e.g. push `(heap_score, sym["id"], candidates_scored, entry)` with the comparison key being `(-heap_score, sym["id"])` via a max-heap transform, mirroring the semantic path's `(-score, symbol_id)` sort.

---

### 4. LOW — Fuzzy standard/full rows echo signature-fallback summaries (jcm#328 regression on one path)

**Location:** fuzzy entry builder in `search_symbols`: `"summary": sym.get("summary", "")`.

**Trigger:** A fuzzy hit on an index built without an AI summarizer, where `summary` is the signature-fallback output (signature truncated to 120 chars), with `detail_level` standard or full. The exact-match path uses `_row_summary(sym)` to suppress the echo; the fuzzy path reads the raw field. `_materialize_full_entry` does not overwrite `summary`, so full-detail fuzzy rows carry it too.

**Impact:** Every fuzzy row duplicates the full signature in the `summary` column — the exact duplication jcm#328 fixed for the exact path, reintroduced on the fuzzy path.

**Fix:** Use `"summary": _row_summary(sym)` in the fuzzy entry builder.

---

No other real defects found in this file: the cache copy-on-get/copy-verdict-on-put discipline is internally consistent with the documented dispatcher write pattern, the single-flight BM25 double-check is correct when `index._bm25_lock` exists, the heap tuple's `candidates_scored` counter prevents dict comparison reaching `entry`, and the semantic path's `new_emb`/`matrix` fallback handles the `matrix is None` case correctly.
