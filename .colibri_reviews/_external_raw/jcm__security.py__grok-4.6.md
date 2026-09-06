=== grok_review | grok-4.6 | sha256 4b2ab9fc5c726324 | C:\Users\User\source\repos\jcodemunch-mcp\src\jcodemunch_mcp\security.py
=== 367s | in=7024 out=23340
==================================================================
**MEDIUM — `should_exclude_file` (`rel_path = file_path.relative_to(root)`)**
- **Trigger:** `root` is resolved (as the docstring requires) and `file_path` is absolute but not resolved, and the two lexical prefixes differ. Happens when the repo lives under a symlinked prefix (`/tmp`, `/var` on macOS → `/private/tmp`, `/private/var`) or `file_path` still contains `..`.
- **Impact:** `validate_path` accepts the file (it resolves), then `relative_to` raises `ValueError` and every file is dropped as `"outside_root"`. Index of that tree is empty.
- **Fix:** Compute relpath from resolved paths, e.g. `file_path.resolve().relative_to(root.resolve()).as_posix()` (same pair `validate_path` already uses). Do not use the unresolved `file_path` against a resolved `root`.

**MEDIUM — `is_secret_file` / `should_exclude_file`**
- **Trigger:** `exclude_secret_patterns` is set in `.jcodemunch.jsonc` (project config), or is a string rather than a list (`"*.pem"` / `"*secret*"`).
- **Impact:** `_config.get(...)` is called with no `repo`, so project overrides are silently ignored (same class as #300 / #390 / #391 in this file). `list()` on a string iterates characters; `"*.pem"` becomes allow patterns `*`, `.`, `p`, `e`, `m`. If `*` is treated as a glob (this module’s own contract), secret detection is effectively disabled.
- **Fix:** Add `repo` to `is_secret_file` and `should_exclude_file` and pass it through to `_config.get`. Require a list: `excluded = _config.get("exclude_secret_patterns", [], repo=repo); excluded = excluded if isinstance(excluded, list) else []`.

**MEDIUM — `_excluded_skip_directories` / `get_skip_directories` / `get_skip_patterns`**
- **Trigger:** `exclude_skip_directories` is set only in project config.
- **Impact:** `_config.get("exclude_skip_directories", [])` has no `repo`, so the opt-out never applies for that corpus. Directories the user explicitly un-skipped (`archive/`, `backup/`, …) stay skipped.
- **Fix:** Take `repo: Optional[str] = None` on all three and pass `repo=repo` into `_config.get`, matching `get_respect_cachedir_tag` / `get_max_folder_files`.

**LOW — `is_binary_extension` / `BINARY_EXTENSIONS` (`.min.js.map`, `.min.css.map`)**
- **Trigger:** Path whose name ends with `.min.js.map` or `.min.css.map`.
- **Impact:** `os.path.splitext` yields `.map`, which is not in the set. Those two entries never match; source maps are not treated as binary.
- **Fix:** Match with `name.endswith(...)` (or check the full suffix string), not `splitext` alone, for the multi-dot entries — or add `.map` if every `*.map` should be excluded.

**LOW — `should_exclude_file` (`check_binary` branch)**
- **Trigger:** `check_binary=True` and the file has no listed binary extension but contains NUL bytes (extensionless ELF/object, misnamed blob, UTF-16, …).
- **Impact:** Only `is_binary_extension` runs; `is_binary_file` / `is_binary_content` are never used. The file is not excluded (size cap is the only backstop).
- **Fix:** After the size check, if `check_binary`: `if is_binary_file(file_path): return "binary_content"` (extension fast-path is already inside `is_binary_file`).

**LOW — `get_skip_directories` vs `_SKIP_DIRECTORY_GLOBS`**
- **Trigger:** `exclude_skip_directories` contains `*.xcodeproj` or `*.xcworkspace` (the user-facing glob).
- **Impact:** `SKIP_DIRECTORIES` stores the derived regex `[^/]*\.xcodeproj`, not `*.xcodeproj`, so the filter `d not in excluded` never removes it. Folder indexing still skips those dirs; `get_skip_patterns` *does* drop `*.xcodeproj/` — the two index paths disagree.
- **Fix:** Compare exclusions against the original glob names (and/or the derived regex), not only exact `SKIP_DIRECTORIES` strings.
