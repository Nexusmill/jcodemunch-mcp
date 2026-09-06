# Colibri review — src/jcodemunch_mcp/tools/index_repo.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\index_repo.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `grok-4.3` review, `.colibri_reviews/_external_raw/jcm__index_repo.py__grok-4.3.md`)
- sha256: `9ae704670302279a3c9b791ed8645ea8c3261bf6a4218610f0cbc24544a43eef` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
One confirmed silent gap: a changed file whose GitHub fetch fails loses its symbols until the next run, with no warning.

## Bugs & vulnerabilities
**[MEDIUM] Fetch failures are dropped silently and delete the file's symbols — CONFIRMED (downgraded from HIGH: self-healing next run)** - `line 495-502, 513-514, 556-557, 572`
- What: `fetch_with_limit` maps any exception to `""`; the builder skips empty content, so a changed file (blob-sha diff, 463-468) is in `changed` but absent from `raw_files_subset`. `incremental_save(changed_files=changed, ...)` then DELETES its symbols (sqlite_store 1947-1950) and inserts nothing; the result carries no warning.
- Mitigation already present: failed fetches keep their old blob sha (569-571) so the next run retries — the gap is transient but invisible.
- Fix: collect failed paths, exclude them from `changed`, and surface them in `warnings`.

## Note on the raw review
- The external review's Finding 2 was cut off by the reviewer's output limit; the visible fragment describes the incremental consequence above and is folded into it.

## Fixed 2026-09-06 (remediation item 7, TDD, gated commit)
- **MEDIUM silent fetch-failure symbol deletion - FIXED** as the record's fix line says:
  `fetch_with_limit` records failed paths; on the incremental path they are removed from
  `changed` / `new` before `incremental_save` (their symbols stay, their old blob sha is kept
  so the next run retries) and a warning names them; a run where every change failed to fetch
  returns "No changes detected" WITH that warning. Test:
  `tests/test_index_repo_fetch_failures.py` - two changed files, one fetch raises: the other
  file updates, the failed file's symbols survive, `changed == 1`, the warning names the file,
  blob shas are old/new respectively; RED on the old bytes (`foo` deleted), GREEN now.
- Open (surfaced, not fixed): the FULL (non-incremental) path has the same shape one level
  up - a file whose fetch fails is simply absent from `current_files` and `save_index` drops it
  from the index without a warning. Out of this finding's scope; recorded here.
