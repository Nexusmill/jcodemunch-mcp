=== hy4_review | z-ai/glm-5.3-flash | sha256 81e350492e5ef155 | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\parser\languages.py
=== 373s | in=17355 out=12242
==================================================================
## Findings — `parser/languages.py`

### 1. LOW — `extra_extensions` keys without a leading dot are silently accepted and never match
**Symbol:** `_apply_extra_extensions()` (the `LANGUAGE_EXTENSIONS[ext] = lang` assignment)
**Trigger:** User config supplies `{"py": "python"}` (or `{"py": ...}` via the env-var fallback) instead of `".py"`. The value is validated only for emptiness and language-name validity, then stored verbatim. All lookups in `get_language_for_path` compare against `os.path.splitext()` output (always dot-prefixed) or `base[first_dot:]` (also dot-prefixed), so a dot-less key can never be hit.
**Impact:** The custom extension is silently inert — files the user intended to index are skipped with no warning, and the config load "succeeds".
**Fix:** Normalize or reject: `if not ext.startswith("."): logger.warning(...); continue` (or store `ext if ext.startswith(".") else "." + ext`).

### 2. LOW — HASKELL_SPEC references a non-existent node type `type_synon`
**Symbol:** `HASKELL_SPEC` (`symbol_node_types` / `type_patterns`)
**Trigger:** Any `.hs` file containing a `type X = ...` synonym. The serokell tree-sitter-haskell grammar names this node `type_synonym`; `type_synon` matches nothing, so those declarations are silently never emitted.
**Impact:** Type synonyms are missing from the index (muted by the fact that `name_fields` is empty for Haskell anyway, so the whole spec yields nameless placeholders — but the miss is silent either way).
**Fix:** Rename to `"type_synonym"` in both `symbol_node_types` and `type_patterns`.

### 3. LOW — Extension collisions with no disambiguation, unlike the handled `.m` case
**Symbols:** `LANGUAGE_EXTENSIONS` entries `".pp": "pascal"`, `".cl": "commonlisp"`, `".v": "verilog"`, `".pl": "perl"`
**Trigger:** Indexing a repo containing Puppet manifests (`.pp`), OpenCL kernels (`.cl`), Coq sources (`.v`), or Prolog (`.pl`). These extensions are the canonical (in Puppet's and OpenCL's case, exclusive) extension of those ecosystems.
**Impact:** Silent misclassification: the file is routed to the wrong custom parser (e.g. `_parse_pascal_symbols` on a Puppet manifest), yielding zero or garbage symbols while the file still appears "indexed". The file explicitly built a disambiguation hook for `.m` (`_looks_like_matlab_path`); no equivalent exists here and no comment marks these as accepted collisions.
**Fix:** Either add path/basename heuristics analogous to the `.m`/`.yaml` handling, or document these as deliberate in the map comments so the behavior is not silent.

### 4. LOW — Ansible basename heuristic misfires on generic filenames
**Symbol:** `_looks_like_ansible_path()` / `_ANSIBLE_BASENAMES`
**Trigger:** Any repo (Ansible or not) containing a top-level `site.yml` or a `requirements.yml`/`requirements.yaml` that is not an Ansible galaxy/requirements file (both are common generic names — e.g. dependency manifests for other tools). The basename check fires before any content or directory-context validation, and overrides the plain `yaml` mapping at step 2 of `get_language_for_path`.
**Impact:** Those files are parsed by the Ansible path instead of the YAML path; symbols/silence differ from expectations with no indication why.
**Fix:** Require additional context for the weakest signals (e.g. only treat `site.yml`/`requirements.yml` as Ansible if an ansible marker appears elsewhere in the path — `roles/`, `playbooks/`, `group_vars/`), or drop them from the unconditional basename set.

No other real defects found in this file: the lazy-init flag/lock in `_apply_extra_extensions` is correct (flag check and set are both inside the lock, and every reader path funnels through it), the `roles/<role>/<segment>` index arithmetic in `_looks_like_ansible_path` is correct (`idx + 2 >= len(parts)` guard matches the intended offset), and the step-6 template fallback can only convert unresolved paths into a language as documented.
