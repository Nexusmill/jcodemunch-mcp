# Colibri review — src/jcodemunch_mcp/config.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\config.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `z-ai/glm-5.3-flash` review, `.colibri_reviews/_external_raw/jcm__config.py__z-ai-glm-5.3-flash.md`)
- sha256: `78678210ba3a2cdddbdfa9963752315be0bde43add676cfc82f8d1462fd39429` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
Shippable with one real trap: two valid JSONC comment shapes make the whole config silently revert to defaults. Probe-confirmed on current bytes.

## Bugs & vulnerabilities
**[MEDIUM] `_strip_jsonc` strips required commas next to comments — CONFIRMED (probe)** - `line 620-623, 633-635`
- What: pass 1 pops a comma that sits immediately before `//` and skips a comma immediately after `*/`.
- Probe (current bytes, `.venv` python): `{ "port": 8901,// c\n "host": "x" }` and `{ "a": 1 /* n */, "b": 2 }` both produce output `json.loads` rejects ("Expecting ',' delimiter"). The external review's other two shapes (`8901, // c` with a space; `1, /* n */` + newline) parse fine, so the defect is narrower than reported.
- Impact: `load_config` catches the `JSONDecodeError` (805-807) and substitutes `DEFAULTS` for EVERY key with one `logger.error`; `load_project_config` (1253-1260) drops the whole project overlay the same way.
- Fix: delete both pass-1 comma heuristics; pass 2 (681-687) already removes genuine trailing commas correctly.

**[MEDIUM] Project `trusted_folders` accepts absolute entries verbatim — CONFIRMED (gap), impact bounded** - `line 1230-1233 vs 1200-1229`
- What: relative and `./` entries are contained to the project root; absolute entries are not. The trust gate reads the key with `repo=str(folder_path)` (index_folder 1437-1439) AFTER `load_project_config` (index_folder 1428), and `get()` makes the project overlay REPLACE the global list for that repo.
- Trigger: a cloned repo ships `.jcodemunch.jsonc` with `"trusted_folders": ["C:\\"]` (whitelist mode) or any list at all (blacklist mode: the replacement drops the global blacklist).
- Impact: limited to the trust decision for indexing that same folder (the broad-root guard and whitelist membership); no other operation consults the key. Still a validation gap the relative-path containment shows was not intended.
- Fix: reject absolute entries in project configs (global keeps them), and consider merging rather than replacing for this key.

**[LOW] Shallow copy of `DEFAULTS` on the create_missing=False path — CONFIRMED (code), impact latent** - `line 812`
- The two sibling paths deepcopy (755, 807, 810). No in-repo mutator of a nested default was traced, so this is a consistency fix.

**[LOW] Negative cache documented but never written — CONFIRMED (code), reach narrow** - `line 924, 932-954`
- `_resolve_repo_key` returns `None` without caching it, so an unresolvable identifier re-runs `IndexStore.list_repos()` on every `get(..., repo=)`. Live callers pass resolved paths (`is_language_enabled("sql", repo=str(folder_path))`, index_folder 798; `get_max_file_size(repo=...)`, 1030) that hit `_PROJECT_CONFIGS` directly because `load_project_config` inserts an empty overlay even without a file (1274-1276). Store a NOT_FOUND sentinel.

**[LOW] `set_config_value`/`unset_config_value` fail on BOM files — CONFIRMED** - `line 1837, 1842`
- Read with `utf-8` while the loaders use `utf-8-sig` (750, 1174); the verification `json.loads` rejects the BOM → rollback + `ValueError` on every set.

**[LOW] Parse failure leaves a stale content hash — CONFIRMED** - `line 1178-1180, 1253-1260`
- The handler writes `{}` but keeps `_PROJECT_CONFIG_HASHES[repo_key]`; reverting the file to its last-good content hits the early return and keeps the empty overlay. Pop the hash in the handler.

**[LOW] `bool` accepted for int/float keys — CONFIRMED** - `line 711-712`

**[LOW] One bad global `trusted_folders` entry discards the whole config — CONFIRMED** - `line 782-785, 808-810`
- Every other key warns and skips; this one raises into the outer handler, which resets everything to defaults.

**[LOW] Unlocked read-modify-write of `.jcodemunch.jsonc` — CONFIRMED** - `line 315, 334`
- Concurrent watcher/manual runs can lose an adaptation or read a half-written file (plain `write_text`, no temp+replace).

## Missing safeguards
- No round-trip test corpus for `_strip_jsonc` covering comment/comma adjacency.
- No atomic-write helper for the project config.

## Fixed 2026-09-06 (remediation item 7, TDD, gated commit)
- **MEDIUM `_strip_jsonc` comma heuristics - FIXED.** All three first-pass comma heuristics are
  gone (the `//` pop, the `*/,` skip, and the `*/\n` walk-back - which, probed, popped the
  trailing SPACE rather than the comma it found, so it was a no-op by accident); comments are
  simply removed and the second pass alone decides trailing commas before `}` / `]`. Test:
  `tests/test_jsonc_comment_comma_adjacency.py` - eleven adjacency shapes round-trip through
  `json.loads`; the two recorded shapes were RED (`Expecting ',' delimiter`), GREEN now, the
  nine already-working shapes pinned; `tests/test_config.py` + `test_config_set.py` unchanged
  and green.
- The other MEDIUM (project `trusted_folders` absolute entries) and the LOWs are still open.
