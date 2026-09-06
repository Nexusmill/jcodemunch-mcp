=== hy4_review | z-ai/glm-5.3-flash | sha256 9e93dc206571a106 | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\storage\index_store.py
=== 180s | in=11763 out=8470
==================================================================
## Findings

### 1. MEDIUM — `CodeIndex.get_symbol` returns the live internal dict, not a copy
**Location:** `get_symbol`, the `return sym` fast path (after the `_INTERNAL_KEYS` check).
**Trigger:** Any caller mutates the dict returned by `get_symbol` for a symbol that has no BM25 cache keys attached (the common case — the copy is only made when internal keys are present).
**Impact:** The returned dict *is* the object stored in `self._symbol_index` and `self.symbols`, so mutation silently corrupts the in-memory index for the lifetime of the process (and anything subsequently persisted from it). This directly contradicts the method's own docstring ("Returns a shallow copy"). Note the asymmetry: symbols *with* BM25 keys get a copy; clean symbols get aliased.
**Fix:** Always return `{k: v for k, v in sym.items()}` (or `dict(sym)`), or document that the result is read-only and enforce it.

### 2. MEDIUM — `CodeIndex.search` leaks internal BM25 keys into results
**Location:** `search`, both return paths (`return [sym for _, _, sym in ...]`).
**Trigger:** BM25 enrichment has run (per `_get_symbol_raw`'s docstring, `_tokens`/`_tf`/`_dl` are attached to the live symbol dicts), then `search` is called. `search` iterates `self.symbols` and returns the raw dicts.
**Impact:** The class comment states these keys "must not leak into API responses" and `get_symbol` exists to strip them — but `search` returns them unstripped, so tool payloads include token arrays/term-frequency dicts (response bloat and contract violation; on large symbols this is significant memory/serialization cost).
**Fix:** Strip via the same filter in both return paths, e.g. `[{k: v for k, v in sym.items() if k not in self._INTERNAL_KEYS} for ...]`, or strip at the point where BM25 keys are attached.

### 3. MEDIUM — lossy slug→(owner, name) round-trip in `list_repos`
**Location:** `list_repos`, Pass 1 corrupted-DB handler (`parts = slug.split("-", 1)`) and the eager-migration loop (`slug = json_path.stem; parts = slug.split("-", 1)`).
**Trigger:** Any repo whose *owner* contains a hyphen (perfectly legal on GitHub, e.g. `my-org/myrepo` → db file `my-org-myrepo.db`). The slug format `f"{safe_owner}-{safe_name}"` is ambiguous and `split("-", 1)` splits at the wrong separator.
**Impact:**
- Corrupted-DB fallback: `inspect_index("my", "org-myrepo")` is queried and the reported `repo` becomes `"my/org-myrepo"` — wrong identity surfaced to the user, and any downstream `delete-index` advice derived from it targets the wrong repo coordinates.
- Eager migration: `inspect_index(owner, name)` and `migrate_from_json(json_path, owner, name)` are called with the mis-split pair; if `migrate_from_json` trusts the passed owner/name for the stored identity, the migrated index is registered under the wrong `owner/name` permanently.
**Fix:** Store owner/name in a sidecar or derive them from the JSON payload's `repo` field (`"owner/name"`) instead of reverse-engineering the slug; the slug must be treated as one-way.

### 4. LOW — `_safe_repo_component` sanitization creates slug collisions
**Location:** `_safe_repo_component` (`re.sub(r"[^A-Za-z0-9._-]", "-", value)`).
**Trigger:** Two distinct repos whose owner/name differ only in sanitized characters, e.g. `("my org", "repo")` and `("my-org", "repo")` — both slug to `my-org-repo`.
**Impact:** The second index silently overwrites/shares the first's db, content dir, and sidecars — silent cross-repo data replacement with no error.
**Fix:** After sanitization, detect the collision (e.g. append a short hash of the original value when `value != sanitized`, or reject when the sanitized slug already maps to a different original).

### 5. LOW — `_load_index_json_cached` caches transient failures as `None`
**Location:** `_load_index_json_cached` — the `except Exception: return None` path is inside the `lru_cache`-wrapped function.
**Trigger:** A transient read failure (file locked by a concurrent writer on Windows, partial write) or a parse error while `mtime_ns` is unchanged on the next call.
**Impact:** The `None` ("invalid") verdict is memoized for that (path, mtime), so `inspect_index` keeps reporting `json_invalid` for a file that is now readable, until its mtime changes. Related: `inspect_index` does `index_path.exists()` then `index_path.stat()` — a delete between the two raises an unhandled `FileNotFoundError`.
**Fix:** Move the try/except outside the cached function (cache only successful parses), and wrap the `stat()` in the caller or use a single `try: stat` block.

### 6. LOW — `_index_to_dict` drops fields the current schema defines
**Location:** `_index_to_dict`.
**Trigger:** Any caller serializing a `CodeIndex` through this method (it is the only to-dict serializer in this file).
**Impact:** `branch`, `git_root`, `source_roots`, `file_sizes`, `package_names`, `file_cap_status`, `coverage`, `alias_map`, and `psr4_map` are silently omitted — a round-trip through this method silently downgrades the index (e.g. losing `parser_generation`-adjacent metadata like `coverage`/`file_cap_status` turns "unknown" into wrong absence claims, and losing `source_roots` breaks v1.96 subdir merging on reload). If this method is dead code, remove it; if it feeds any write path, this is data loss.
**Fix:** Either delete the method or make it schema-complete (ideally by iterating the dataclass fields so future additions can't be forgotten).

### Not reported (checked and clean)
- `_safe_content_path` traversal guard (symlinks resolved; correct).
- `search` bounded-heap logic (counter tiebreak prevents dict comparison; correct).
- `_verify_checksum` always returning `True` on mismatch is explicitly documented as deliberate.
- `parser_generation` defaulting to `0` is explicitly documented as deliberate.
- `delete_index` preserving unmigrated JSON is deliberate and correctly implemented.
