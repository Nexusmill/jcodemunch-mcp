=== hy4_review | z-ai/glm-5.3-flash | sha256 fd3453f2c83e283a | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\investigator\deletion_safety.py
=== 57s | in=5069 out=4877
==================================================================
## Findings

### 1. HIGH — `no_textual_use`: a failed text sweep is reported as SATISFIED (silent failure)

**Location:** `investigate_deletion_safety`, Obligation 3 block:

```python
hits = search_text(repo, target_name, storage_path=storage_path)
text_ob.calls = 1
results = hits.get("results") or []
```

**Trigger:** `search_text` returns an error payload (`{"error": ...}`) — bad index state, storage failure, tool-level refusal — instead of results.

**Impact:** Unlike Obligation 2, which explicitly checks `if "error" in refs`, this code never inspects `hits` for an error key. `hits.get("results") or []` evaluates to `[]`, `other_files` is empty, and the obligation is marked `SATISFIED` with the evidence `"appears only in its own file"`. A failed sweep is indistinguishable from a clean sweep. Since this is a STATIC obligation, a sweep error can directly produce a `SAFE` verdict. This is precisely the "UNESTABLISHED collapsed into SATISFIED" failure the module's own docstring says it exists to prevent.

**Fix:** Mirror Obligation 2:

```python
if "error" in hits:
    text_ob.status = UNESTABLISHED
    text_ob.evidence.append(f"Text sweep failed: {hits['error']}")
    text_ob.calls = 1
    obligations.append(text_ob)  # (existing flow)
else:
    results = hits.get("results") or []
    ...
```

---

### 2. HIGH — `_split_importers_by_liveness` classifies entry-point files as dead

**Location:** `_split_importers_by_liveness`:

```python
if int(res.get("importer_count", 0) or 0) == 0:
    dead.append(f)
```

**Trigger:** Any importer file that is itself a root of the import graph — a script (`scripts/*.py`), `__main__.py`, a test file, a notebook-adjacent module, a `bin/` entry. Such files have zero importers *by definition* yet are fully reachable at runtime.

**Impact:** The docstring claims "An importer we cannot classify counts as REACHABLE, so uncertainty blocks deletion" — but zero-importer files *are* classified, as dead, with no entry-point check. The module already has `_detect_entry_point`, but it is applied only to the target symbol, never to the importer files being liveness-classified. Consequence: a symbol imported and used only by `scripts/migrate.py` gets its importers classified dead → `export_not_imported` becomes SATISFIED (with a `deletion_cluster`) → potentially a `SAFE` verdict for a symbol that is actively executed. Same false-satisfaction propagates through the `no_textual_use` liveness qualifier.

**Fix:** Before appending to `dead`, run an entry-point/root heuristic on `f` (reuse `_detect_entry_point` on the file's record, or at minimum treat paths under `scripts/`, `bin/`, `tests/`, `__main__.py`, and files with `if __name__ == "__main__"` as live). Anything not positively classifiable as dead should fall into `live`, per the function's own stated contract.

---

### 3. MEDIUM — `deletion_cluster` override clobbers the do-not-delete action under an UNSAFE verdict

**Location:** end of `investigate_deletion_safety`:

```python
if cluster:
    result["deletion_cluster"] = cluster
    result["recommended_next_action"] = (
        "Removable only as a group. These importers are themselves "
        f"unreachable and must go with it: {', '.join(cluster)}"
    )
```

**Trigger:** Verdict is `UNSAFE` (e.g., `not_entry_point` REFUTED, or runtime hits > 0) *and* `export_not_imported` was SATISFIED via the dead-importer path, populating `deletion_cluster`. This is realistic: a framework entry-point handler that is also imported by one dead script.

**Impact:** The unconditional override replaces the `"Do not delete. ..."` action with `"Removable only as a group. These importers ... must go with it"` — an instruction to delete, directly contradicting the `unsafe` verdict sitting one field above it. An agent consuming `recommended_next_action` will act on the deletion instruction.

**Fix:** Gate the override on a permissive verdict:

```python
if cluster and verdict in (SAFE, STATIC_CLEAR):
    ...
```

---

### Non-findings (checked, not defects)

- `_verdict` tri-state logic is sound: REFUTED short-circuits, `SAFE` requires all-SATISFIED, `STATIC_CLEAR` requires all STATIC obligations SATISFIED (a REFUTED static obligation can't reach it because REFUTED returns first), and `NOT_ESTABLISHED` correctly implies at least one UNESTABLISHED static obligation, so `unresolved[0]` in the else-branch cannot IndexError.
- Exception fallbacks in `_split_importers_by_liveness` and the per-obligation `except` blocks all fail toward UNESTABLISHED/live, which is the safe direction.
- The `blockers[0].evidence[0]` access in the UNSAFE action is guarded against an empty evidence list.
