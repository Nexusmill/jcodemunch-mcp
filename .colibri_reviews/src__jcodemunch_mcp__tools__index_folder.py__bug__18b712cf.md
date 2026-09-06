# Colibri review — src/jcodemunch_mcp/tools/index_folder.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\index_folder.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `grok-4.3` review, `.colibri_reviews/_external_raw/jcm__index_folder.py__grok-4.3.md`)
- sha256: `18b712cf3be2932748c3738c540f87e8bacbd7bdbad3b79f1581d75dc05cd5fa` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
One real branch-mode defect, worse than the external review described: no-change runs on a feature branch write the branch HEAD into the BASE index.

## Bugs & vulnerabilities
**[HIGH] No-change paths write to the base index regardless of branch — CONFIRMED** - `line 958-991 (called 1870, 2451), 1948-1954`
- What: `_refresh_git_head_if_advanced` and the mtime-only block call `store.incremental_save` unconditionally, while the real-change paths correctly switch on `_fast_is_branch_delta` / `_is_branch_delta` (1994-2025, 2536-2569).
- Trigger: watcher or manual incremental run on a non-base branch with no indexable content change (a commit touching only non-indexed files, or mtime-only drift).
- Impact: the BRANCH's HEAD (and branch-file mtimes) is stamped into the base index meta. The base is now "at" a commit it was never indexed at; `load_index` then warns the delta is stale (`base_head != index.git_head`, 1589-1596) on every branch load, and the branch delta's own `git_head` never advances so `FreshnessProbe` keeps flagging the branch stale — the exact symptom #330 tried to remove.
- Fix: thread the active branch into `_refresh_git_head_if_advanced` and the mtime-only block; when set, call `save_branch_delta(..., changed_files=[], new_files=[], deleted_files=[], git_head=..., file_mtimes=...)`.

## Refuted external findings
- MEDIUM `_needs_parser_upgrade(_fast_base_index)` (1797) "disarms the branch delta path": the full path it falls to is itself branch-aware (2248-2266) and re-checks the upgrade on the composed index (2281). Cost is one extra load, not a correctness loss.
- LOW `post_discovery_drops` not recorded when `paths=` is given: deliberate (2575-2577, 2912-2914) — a subset refresh must not overwrite the whole-corpus coverage contract.

## Fixed 2026-09-06 (remediation item 3, TDD, gated commit)
- **Root cause was one layer deeper than the HIGH above.** The base index's branch was never
  persisted OR read back: `save_index` wrote meta `base_branch` from `CodeIndex.branch`, which no
  writer ever set, and `_build_index_from_rows` never read the key. Every loaded base therefore
  carried `branch == ""`, index_folder's "base IS this branch" fallback (2294-2297, 1781-1783) made
  `_is_branch_delta` unreachable on the first switch, and a feature branch's whole content - not
  just its HEAD - was `incremental_save`d into the base. Probe: fresh `index_folder` on `main`,
  meta `base_branch == ''`, `list_branches == []` while on `feature`.
- Fix (three files, minimal): `_build_index_from_rows` reads `base_branch` into `CodeIndex.branch`;
  `save_index` (sqlite + the `IndexStore` facade, which had silently dropped the kwarg) takes
  `branch=`; index_folder passes `_current_branch` at both base-creating `save_index` sites
  (2861, 2928). Plus the HIGH's own fix: `_refresh_git_head_if_advanced(..., branch=)` and the
  mtime-only block write `save_branch_delta` (empty lists, `base_head` carried through) in
  delta mode instead of `incremental_save`.
- Tests (RED first, then GREEN): `tests/test_branch_no_change_head.py` - base branch persisted;
  full-walk no-change run on `feature` advances the branch meta, base git_head untouched;
  watcher mtime-only run likewise; helper unit tests (base_head preserved / derived).
- **Gate round 1 (grok, 2026-09-06 00:32) caught a real hole in the first fix - CONFIRMED against
  the bytes:** `_patch_index_from_delta` (the warm-cache rebuild used by `incremental_save`)
  constructed its CodeIndex without `branch=`, so ONE base-mode incremental save in a long-lived
  process (watcher edit, deferred summarizer, the base-mode head refresh) re-cached the base with
  `branch == ""` and re-armed the fallback until a process restart. Fixed by carrying
  `meta["base_branch"]` (falling back to `old.branch`) in that constructor; two more RED->GREEN
  tests (`TestWarmCacheKeepsBaseBranch`): base-mode no-change run keeps `branch == "main"`
  in-process, and a branch switch AFTER a warm incremental save still takes delta mode.
- **Gate round 2 (grok, 00:55) accepted the warm-cache fix and raised three findings about
  branch-delta paths that this change makes reachable for the first time.** Verified against
  the bytes:
  - HIGH, FIXED: the watcher fast path's deferred-summarizer thread fired after a
    `save_branch_delta` too, and its `_run_deferred_summarize` saves through a branch-less
    `incremental_save` - the feature branch's parsed symbols landed in the BASE (default
    `use_ai_summaries=True`). Guard: no deferred thread in delta mode (branch symbols keep
    their inline summaries). Test: `test_fast_path_delta_does_not_start_the_base_summarizer_thread`
    (RED: a `deferred-summarizer` thread was constructed; GREEN now).
  - LOW, FIXED: both delta paths called `_record_coverage`, which writes the BASE meta's
    coverage contract with the branch's walk numbers. Guard: `and not _is_branch_delta` at both
    sites. Test: `test_delta_full_walk_does_not_rewrite_base_coverage` (RED: files_indexed 1->2).
  - **MEDIUM, CONFIRMED, NOT FIXED HERE (open):** `_save_branch_delta_locked` writes the
    branch's raw file text into the SAME per-repo content dir the base uses
    (`_content_dir(owner, name)`, sqlite_store 1047-1055), while `get_symbol_content` /
    `get_file_content` are branch-unaware and slice by the base symbols' offsets. While a
    delta with a modified file exists, base-view source reads of that file return branch
    bytes at base offsets. This is a design defect of the delta subsystem (pre-existing; it
    simply never ran because delta mode was unreachable) and the fix is branch-scoped content
    storage PLUS branch-aware readers - a feature-sized change outside this remediation.
    Trade-off stated plainly: before this commit a branch switch overwrote the whole base
    with branch content (self-consistent but wrong everywhere); after it the base symbols are
    right and only the modified files' source slices can be wrong while the delta exists.
    Docketed as the next item for this file.
    **Design 2026-09-06:** Nexusmill repo
    `docs/superpowers/specs/2026-09-06-jcm-branch-scoped-content-design.md` (this fork
    gitignores `docs/`; planning docs for jcm live in Nexusmill's spec tree)
    (B1 storage design + the stale-row defect it fixes; B2 = tools follow the checkout).
    Two facts the docket wording missed, verified against the bytes: NO retrieval tool ever
    loads a branch view (composed indexes serve only index_folder/index_file), and the
    full-walk path writes EVERY walked file into the base dir (2666-2687), not just the
    delta save. Live storage 2026-09-06: 33 indexes, 0 deltas - nothing poisoned yet.
    Awaiting the owner's ruling (spec section 4) before implementation.
- Caveat (surfaced, not fixed): bases indexed BEFORE this fix carry `base_branch == ''` until
  their next full `save_index` (a `force`/non-incremental `index_folder`); `incremental_save`
  does not stamp it, so those legacy DBs keep the old fallback until re-indexed once.
