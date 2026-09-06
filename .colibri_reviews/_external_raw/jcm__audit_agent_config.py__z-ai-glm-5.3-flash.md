=== hy4_review | z-ai/glm-5.3-flash | sha256 e68d3bcdfac0a421 | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\audit_agent_config.py
=== 483s | in=6866 out=6954
==================================================================
## Findings

### 1. MEDIUM — `lstrip("./")` is a character-set strip, not a prefix strip (two call sites)

**Location:** `_check_dead_paths` — `normalized = ref.lstrip("./")`; same bug in `_resolve_section_refs` — `normalized = _norm(ref).lstrip("./")`.

**Trigger:** Any file reference whose path after the `./` prefix begins with a dot character, e.g. `` `./.github/workflows/ci.yml` `` or `` `./.cursor/rules/x.mdc` `` in a config file. `lstrip("./")` strips *all* leading `.` and `/` characters, so `"./.github/workflows/ci.yml"` becomes `"github/workflows/ci.yml"` instead of `".github/workflows/ci.yml"`.

**Impact:** The suffix match against `source_files` fails (indexed paths contain the `.github/` segment), the `os.path.exists(source_root + normalized)` fallback also checks the wrong path, and the user gets a false `dead_path` finding for a file that exists and is indexed. In `_resolve_section_refs` the same corruption silently drops valid references from the skill-candidate concentration calculation, skewing `concentration` and `minResolvedRefs` gating.

**Fix:** Replace with an explicit prefix removal:
```python
normalized = _norm(ref)
if normalized.startswith("./"):
    normalized = normalized[2:]
```
in both places (and note `_check_dead_paths` additionally needs the `_norm` treatment for Windows-separated refs to match `source_files` consistently).

---

### 2. LOW — `_check_dead_paths` suffix match has no path-separator boundary

**Location:** `matched = any(sf.endswith(normalized) or sf == normalized for sf in source_files)`.

**Trigger:** A referenced path that is a suffix of a longer path component, e.g. ref `src/foo.py` vs. indexed file `mysrc/foo.py` — `"mysrc/foo.py".endswith("src/foo.py")` is `True`.

**Impact:** False negative: a genuinely dead path is reported as existing because an unrelated file with a matching character suffix (without a `/` boundary) satisfies the check.

**Fix:** Match on `"/" + normalized` (after `_norm(sf)`) or on `sf == normalized or sf.endswith("/" + normalized)`, as `_resolve_section_refs` already does correctly.

---

### 3. LOW — partial index-load failure leaves inconsistent cross-check state

**Location:** `audit_agent_config`, the `try` block around `store.load_index(...)` through `source_root = index.source_root or ""`.

**Trigger:** An exception raised *after* `index = store.load_index(...)` succeeds but before `source_files`/`source_root` are assigned (e.g. `AttributeError` on `index.source_files`, or an error building `symbol_files`). The single `except Exception` catches it, but `index` remains truthy.

**Impact:** The function proceeds with `index` set, `all_symbol_names`/`symbol_files` populated, but `source_files = set()` and `source_root = ""`. `_check_dead_paths` then reports *every* file reference as a dead path (empty `source_files`, no on-disk fallback since `source_root` is empty), and the failure is only visible at `logger.debug` level. The user gets a page of false findings instead of "index unavailable".

**Fix:** In the `except` handler, reset `index = None` (and the derived sets) so a partial load degrades to the same "no index" path as a failed load.

---

### 4. LOW — `.cursor/rules` check silently never fires for the real Cursor layout

**Location:** `_PROJECT_CONFIGS` entry `(os.path.join(".cursor", "rules"), "Cursor rules (new)")` combined with the `if p.is_file()` gate in `_discover_files`.

**Trigger:** Any project using current Cursor, where `.cursor/rules` is a *directory* of `*.mdc` rule files, not a single file.

**Impact:** `p.is_file()` is `False`, the entry is silently skipped, and the advertised "Cursor rules (new)" audit covers nothing for the standard modern layout — with no signal to the user that it was skipped. (The same silent-skip applies if the path is a symlink to a directory.)

**Fix:** If `p.is_dir()`, iterate `p.glob("*.mdc")` (or `rglob("*")` filtered to files) and audit each file as a separate entry; otherwise emit a finding/metadata entry noting the unsupported layout instead of dropping it.

---

### 5. LOW — early-return result shape omits keys present in the normal return

**Location:** `audit_agent_config`, the `if not files: return {...}` block.

**Trigger:** Call made with no agent config files found.

**Impact:** The early return omits `global_tokens`, `finding_counts`, and `skill_advisor`, which are always present in the full return path. Any caller that reads those keys unconditionally (e.g. an MCP client rendering `finding_counts` or the `skill_advisor.hint`) gets a `KeyError`/`undefined` on the empty-repo path rather than a zero-value.

**Fix:** Include `"global_tokens": 0`, `"finding_counts": {"warning": 0, "info": 0}`, and the `skill_advisor` dict (with `enabled`/`index_available`/`hint`) in the early return so both paths share one schema.

---

Areas checked with no defects found: `_split_sections` line/end_line arithmetic, `_find_duplicate_runs` run accounting, `_edit_distance`/`_fuzzy_suggest` (band early-exit is correct), `_best_subtree` prefix/share math and empty-input guards, `_H2` vs. `###` heading discrimination, `_check_scope_leaks` `findall` group semantics (all patterns are group-free, so `matches[0]` is the full match and `_find_line` is valid), and the `_FILE_PATH_REF` boundary groups.
