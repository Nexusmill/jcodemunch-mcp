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
    Ruled B by Damien 2026-09-06 (same session): tools will follow the checkout (B2, own spec).

## Fixed 2026-09-06 (B1 - branch-scoped content, two gated commits, TDD)
- **0fe7c3a (storage):** bodies for delta files live in a sibling `<slug>@<branch-slug>-<sha8>`
  dir (`_branch_content_dir`; `_safe_repo_component` never emits `@`); `CodeIndex.delta_files`
  is set only by `compose_branch_index`; `get_symbol_content`/`get_file_content` pick the dir by
  MEMBERSHIP through `_content_root_for` and fail closed (None) on a missing branch body;
  `delete_branch_delta` (now under the `indexwrite` lock) and `delete_index` remove the dirs;
  `save_branch_delta(replace_all=True)` drops the branch's whole row set AND unlinks the bodies
  of the rows it drops. Tests: `tests/test_branch_content_dir.py` (15, RED-first; the defect
  itself reproduced as `'XX = 1\ndef foo('` served for a base read).
  Gate round 1 (gate_20260906-142613) BLOCKed: HIGH "no migration for legacy deltas" REFUTED
  (no version of this fork ever wrote a delta - unreachable before fe2afe5; live probe 33
  indexes / 0 branch_meta rows; the reviewer accepted that zero branch_meta rows is itself
  proof no delta body was ever written); LOW `replace_all` left stale bodies - ACCEPTED, fixed
  (dropped-files unlink); LOW the new rmtree in `delete_branch_delta` ran outside the
  `indexwrite` lock - ACCEPTED, fixed (lock spy test, RED proven by mutating the lock name).
  CLEAR round 2 (gate_20260906-143349).
- **505d365 (index_folder full walk, `incremental=False`):** the base is loaded ONCE before the
  walk (if None the run is a plain base save; the old "no base index" fallback that would have
  saved a body-less base is gone); in delta mode only files whose hash differs from the base's
  get a body, written to the branch dir; the delta save passes `replace_all=True`, so a reverted
  file's stale `modify` row (and its body) goes away. Tests: `tests/test_branch_content_walk.py`
  (8): full walk, revert, failed walk stays readable, subdir refused, base-mode guard, plus
  three pass-through proofs (incremental discovery, watcher fast path, index_file - unchanged
  in code, RED-proven by routing branch bodies to the base dir at class level).
  Gate round 1 (gate_20260906-144626) BLOCKed on TWO real MEDIUMs in my first cut, both
  ACCEPTED: (1) the spec's pre-walk `rmtree` of the branch dir made a mid-walk failure STICKY
  (rows survived without bodies; the next incremental run saw matching hashes and never
  rewrote them) - wipe deleted, the store's dropped-files pass covers stale bodies; (2) a
  subdirectory walk on a branch (`walk_prefix` non-empty) marked every base file outside the
  prefix deleted and, with `replace_all`, dropped the branch's own rows outside it - refused
  explicitly with an error naming prefix/branch/base. CLEAR round 2 (gate_20260906-145217).
  Full suite on the final bytes: 7820 passed / 32 skipped / 0 failed (baseline 7797 + 23).
- **Residuals recorded, not fixed (all pre-existing classes, all fail closed):** `delete_index`'s
  new `@*` rmtree runs unlocked like its base-dir rmtree always has; `dead.unlink()` in the
  branch content pass can raise PermissionError on Windows with a reader holding the body
  (same as `_incremental_save_locked`); `paths=` with `incremental=False` on a branch
  (`walk_prefix == ""` but a file subset) still computes `delta_deleted` over the subset and
  now `replace_all`s - the reviewer judged it "equally wrong" before (deleted markers vs
  dropped rows) and off the normal route; incremental-path subdir walks on a branch keep their
  pre-existing accounting problem. The nine direct `_content_dir` readers still serve the base
  dir (now guaranteed base bytes) - B2 (tools follow the checkout) is next, own spec.
- Lesson (docket EV-040): the spec's "wipe first, then walk" was reviewed by me, the advisor
  and the ruling, and was still wrong - failure ORDERING is a review unit of its own; write the
  "what survives a crash between step N and N+1" test BEFORE choosing the order.
- Caveat (surfaced, not fixed): bases indexed BEFORE this fix carry `base_branch == ''` until
  their next full `save_index` (a `force`/non-incremental `index_folder`); `incremental_save`
  does not stamp it, so those legacy DBs keep the old fallback until re-indexed once.
- Post-commit checks (2026-09-06, after the CLEAR): `delete_branch_delta` now takes the
  non-reentrant `indexwrite` lock - its only callers are the `IndexStore` facade and tests
  (`search_text` over `src/`), so no production path acquires it from inside a locked region.
  Exposure until B2: live storage has exactly three indexes with a non-blank `base_branch`
  (colibri-code-review = main, Nexusmill = main, jcodemunch-mcp = nexusmill-local); on those
  repos an `index_file`/`index_folder` run from any OTHER branch (e.g. a `gate/<name>` side
  branch) writes a delta while every tool keeps serving base bytes - consistent, stale,
  silent. Rule: index those repos only from the base branch; a branch view needs
  `delete_index` + re-index on that branch until B2 lands.
