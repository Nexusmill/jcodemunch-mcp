# Colibri review — src/jcodemunch_mcp/tools/plan_refactoring.py (bug)

- source: `C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\tools\plan_refactoring.py`
- model: claude-fable-5-1 (in-session Phase-3 gate over the external raw `grok-4.3` review, `.colibri_reviews/_external_raw/jcm__plan_refactoring.py__grok-4.3.md`)
- sha256: `0b7ee24fa316fe5b333471234615cc7affdaad239b0ed8caeaea7b5f8de67912` (current bytes at dispatch, 2026-09-05; identical to the bytes the external reviewer saw)
- date: 2026-09-05
- mode: bug
- context pack: jCodemunch symbol map + call-site search on `jcodemunch-mcp`; the external raw review; no prior `.colibri_reviews` record for this file; no remediation manifest exists in this repo. Every external finding was re-traced against the cited lines (Phase 3): CONFIRMED / PLAUSIBLE kept, refuted ones listed with the reason so they are never re-fixed (G35).

## Verdict
Not shippable for TypeScript overload renames: the generated edit deletes the implementation's opening line.

## Bugs & vulnerabilities
**[HIGH] TS overload extraction swallows the implementation line — CONFIRMED** - `line 192, 1331-1338, 1969-1974`
- What: `_TS_OVERLOAD_PATTERN` (`^\s*(export\s+)?function\s+\w+\s*\(.*\)\s*:`) also matches an implementation line (`function f(a: any): any {` — the `):` is there), and the collection loop (1334) accepts every consecutive `function <name>(` line with no overload test. `old_def` therefore spans the signatures AND the implementation's first line; the caller replaces that whole span with ONE `function {new_signature}` line (1974).
- Trigger: any TypeScript symbol with overload signatures directly followed by its implementation (the normal layout).
- Impact: applying the plan removes the implementation's opener/brace — the file no longer parses.
- Fix: an overload line must end with `;` or a type annotation and contain no `{`; stop collecting at the first line containing `{`.

**[MEDIUM] `repo.split("/", 1)` without a guard — CONFIRMED (line 246, not the reported ~80)**
- Every other tool routes through `resolve_repo`; here an identifier-form repo (`jcodemunch-mcp`) or a path raises `ValueError` out of the tool instead of returning `{"error": ...}`.

**[LOW] `_ensure_unique_context_smart` can return a non-unique block — CONFIRMED** - `line 1285-1309`
- After the 5-line expansion budget there is no uniqueness re-check, so identical duplicate blocks longer than the budget yield an ambiguous `old_text` presented as an edit block. Flag the edit as ambiguous when `content.count(old_text) > 1` after the loop.
