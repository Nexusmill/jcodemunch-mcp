=== hy4_review | z-ai/glm-5.3-flash | sha256 78678210ba3a2cdd | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\config.py
=== 535s | in=26693 out=23213
==================================================================
## Findings

### 1. MEDIUM — `_strip_jsonc` strips *required* commas adjacent to comments, making valid JSONC unparseable

**Symbol:** `_strip_jsonc` — line-comment branch (`if result and result[-1] == ',': result.pop()`), and both block-comment comma branches (`if end_i < n and text[end_i] == ','` / the newline walk-back `if j >= 0 and result[j] == ',': result.pop()`).

**Trigger:** Any of these valid JSONC shapes:
```jsonc
{ "port": 8901,// comment
  "host": "x" }                  // comma immediately before // → popped
{ "a": 1, /* note */
  "b": 2 }                       // comma before /* with newline after */ → popped
{ "a": 1 /* note */, "b": 2 }    // comma immediately after */ → skipped
```
**Impact:** `json.loads` fails → `load_config`'s `except json.JSONDecodeError` discards the entire user config and silently substitutes `DEFAULTS` (one `logger.error`). Every setting — including `disabled_tools`, `trusted_folders_whitelist_mode`, `max_file_size` — reverts for the process.
**Fix:** Delete the pass-1 comment-adjacent comma heuristics entirely. The second pass already removes trailing commas correctly (it pops `whitespace ,` only when it actually encounters `}`/`]`). The pass-1 heuristics are redundant and the sole source of the corruption, since they strip a comma without knowing whether another element follows.

### 2. MEDIUM — `load_config` else-branch uses a shallow copy of `DEFAULTS`

**Symbol:** `load_config`, final `else:` branch: `_GLOBAL_CONFIG = DEFAULTS.copy()`.

**Trigger:** Config file absent with `create_missing=False` — i.e., exactly the lazy `_ensure_loaded()` path (#426) on any machine without a config file, which is now a common path, not a corner.
**Impact:** Nested mutables (`tool_tier_bundles`, `model_tier_map`, `trusted_folders`, `extra_extensions`, `descriptions`, `watch_paths`) are shared with `DEFAULTS`. Any caller mutating an object obtained from `get()` (e.g., runtime tier code writing into `model_tier_map`, which the template explicitly invites: "Edit freely") corrupts `DEFAULTS` — poisoning `config_report`'s `default` column and every later `deepcopy(DEFAULTS)` in the same process. The success and exception paths use `deepcopy`; this branch is the inconsistent one.
**Fix:** `_GLOBAL_CONFIG = deepcopy(DEFAULTS)`.

### 3. MEDIUM — `_resolve_repo_key` never writes the documented negative cache; unknown repo → full `IndexStore.list_repos()` on every `get()`

**Symbol:** `_resolve_repo_key` — comment says `# None = negative cache (unknown repo)`, but `updates` only ever contains resolved path strings and `result = None` is returned without being cached.

**Trigger:** Any `get(key, repo=<unknown-or-typoed-identifier>)` — e.g. `is_tool_disabled()` / `is_language_enabled()`, which run per tool call.
**Impact:** Every such read re-constructs an `IndexStore` and re-runs `list_repos()` (directory scan + SQLite open) on the hot path, repeatedly, for the lifetime of the process. Multiple `get()` calls per tool invocation multiply this.
**Fix:** Store a sentinel (e.g. `""` or a dedicated `NOT_FOUND` object) in `_REPO_PATH_CACHE` for identifiers that resolved to nothing, and treat it as `None` on lookup; optionally bound its TTL.

### 4. MEDIUM (security) — project `trusted_folders` accepts unrestricted absolute paths

**Symbol:** `load_project_config`, `trusted_folders` handling, final `else:` branch: `expanded_folder = Path(folder).expanduser().resolve()` — no containment check.

**Trigger:** A repo's `.jcodemunch.jsonc` (repo-authored content, e.g. cloned from an untrusted source) contains `"trusted_folders": ["C:\\", "/home/otheruser"]`. Relative and `./`-prefixed entries are correctly confined to the project root, but absolute entries are accepted verbatim.
**Impact:** If the trust gate resolves trust via `get("trusted_folders", repo=...)` after `load_project_config` has run (the overlay is read by `get()` precisely so project values win), the indexed repo itself can extend the whitelist — or, in blacklist mode, extend the blocklist — to arbitrary directories, defeating `trusted_folders_whitelist_mode`. The containment checks on the relative branches show this is a validation gap, not a deliberate allowance.
**Fix:** Apply the same project-root containment check to absolute entries in project configs, or reject absolute entries outright in `load_project_config` (global config, which is user-authored, can keep accepting them).

### 5. LOW — `set_config_value` / `unset_config_value` always fail on BOM configs

**Symbol:** Both read with `config_path.read_text(encoding="utf-8")` and verify with `json.loads(_strip_jsonc(updated))`.

**Trigger:** Config file saved with a UTF-8 BOM (common on Windows editors; the loaders explicitly acknowledge this by using `utf-8-sig`).
**Impact:** The BOM character survives into `updated`; `json.loads` rejects a leading BOM → verification fails → write is rolled back and a spurious `ValueError("config set failed (rolled back)")` is raised. `config set` / `config unset` are permanently broken for such files.
**Fix:** Read with `encoding="utf-8-sig"` (matching the loaders), or strip a leading `\ufeff` before verification.

### 6. LOW — `load_project_config` failure path leaves a stale content hash, blocking recovery

**Symbol:** `load_project_config`, `except Exception:` branch — sets `_PROJECT_CONFIGS[repo_key] = {}` but does not clear `_PROJECT_CONFIG_HASHES[repo_key]`.

**Trigger:** Config v1 loads fine (hash H1 cached) → user breaks the file (parse error → empty overlay, hash still H1) → user reverts the file to the v1 content.
**Impact:** Next `load_project_config` hits the early-return (`_PROJECT_CONFIG_HASHES.get(repo_key) == content_hash`) and keeps the empty overlay — the now-valid project config is silently ignored until the file changes again.
**Fix:** `_PROJECT_CONFIG_HASHES.pop(repo_key, None)` in the exception handler.

### 7. LOW — bools accepted for int/float keys (`bool` ⊂ `int`)

**Symbol:** `_validate_type` (generic `isinstance(value, expected_type)` path) with `CONFIG_TYPES`.

**Trigger:** `"port": true` → port becomes `True` (== 1); `"max_file_size": true` → every file exceeds the cap and is skipped; `"server_output_threshold": true` → adaptive encoding never fires.
**Impact:** Nonsensical values silently accepted and used; indexing can silently produce an empty index.
**Fix:** In `_validate_type`, reject `isinstance(value, bool)` when the expected type is `int`/`float` (and in `coerce_config_value`, which already handles bool-before-int for coercion but not for the `int in allowed` acceptance of `True`... it does — `isinstance(val, bool)` is checked first there; only `_validate_type` needs the guard).

### 8. LOW — one bad `trusted_folders` entry discards the entire global config

**Symbol:** `load_config`, `trusted_folders` branch: `raise ValueError(...)` inside the per-key loop, caught by the outer `except Exception` → `_GLOBAL_CONFIG = deepcopy(DEFAULTS)`.

**Trigger:** One non-absolute or otherwise bad entry in the global config's `trusted_folders`.
**Impact:** Inconsistent with every other key, which is warned about and skipped: a single typo reverts *all* settings to defaults for the process, with only a log line. (Fail-closed for trust, but silently destructive for everything else.)
**Fix:** `logger.warning(...); continue` for the offending entry, matching the per-key tolerance used everywhere else.

### 9. LOW — `apply_adaptive_languages` performs an unlocked read-modify-write of `.jcodemunch.jsonc`

**Symbol:** `apply_adaptive_languages` (both stages: `local_path.write_text(...)` plus the preceding exists/read/parse sequence).

**Trigger:** Concurrent `index_folder` runs against the same repo (e.g. watcher-triggered reindex overlapping a manual index — the exact concurrency the watcher introduces). Two threads can both pass the `exists()`/adaptive checks and interleave read-modify-write; a concurrent `load_project_config` can also read a partially written file.
**Impact:** Lost update (one thread's language adaptation overwritten) or a transient parse failure caching an empty overlay.
**Fix:** Guard the file's read-modify-write with a per-path lock (or a global one — it's a rare path) and write atomically (temp file + `os.replace`).
