---
phase: 04-client-distribution
plan: 05
subsystem: distribution
tags: [pypi, packaging, twine, py.typed, ci-guard, homeassistant]

# Dependency graph
requires:
  - phase: 01-foundation-package-parser
    provides: "src/aionlslivetiming/py.typed + hatch force-include (D-11)"
  - phase: 04-client-distribution (plans 01-04)
    provides: "NLSClient, CLIs, docs/ tree, README, CHANGELOG, LICENSE, CONTRIBUTING, mkdocs.yml"
provides:
  - "scripts/build.sh — one-shot uv build + twine check sanity wrapper (D-26, D-29)"
  - "scripts/check_no_ha_imports.sh — CI guard against HA imports in src/ and tests/ (D-30)"
  - "tests/test_build.py — 22 automated tests covering py.typed, [project] metadata, no-HA-imports, uv build, twine check"
  - "twine added to [project.optional-dependencies].dev"
  - ".gitignore extended with site/ for mkdocs build output"
affects: [release, ci]

# Tech tracking
tech-stack:
  added:
    - "twine>=6.0 (dev-only)"
  patterns:
    - "Shell CI guards use line-anchored regex to match real import statements only (avoids false positives on test docstrings/comments)"
    - "Test files glob for *.whl and *.tar.gz specifically when iterating uv build output (uv may copy repo files into out-dir)"
    - "build.sh invokes twine via `uv run python -m twine` to use the venv-installed twine, not the system python"

key-files:
  created:
    - scripts/build.sh
    - scripts/check_no_ha_imports.sh
    - tests/test_build.py
  modified:
    - pyproject.toml (added twine>=6.0 to dev extras)
    - .gitignore (added site/)

key-decisions:
  - "Shell check_no_ha_imports.sh regex anchors to `import homeassistant` / `from homeassistant ... import` statements only, matching the Python AST-level concern rather than substring mention"
  - "build.sh uses `uv run python -m twine` instead of `python -m twine` so it works without a system-installed twine"
  - "test_twine_check_passes globs for *.whl + *.tar.gz (not iterdir) because `uv build --out-dir <existing_dir>` may copy repo files like .gitignore alongside artifacts"

patterns-established:
  - "CI script + companion test: shell script checked by test_<script>_executable + test_<script>_exits_zero pair"
  - "Build-time gates (uv build, twine check) integrated as pytest tests so they're enforced in the normal `pytest` run, not just a separate make/CI step"

requirements-completed: [DIST-01, DIST-04]

# Metrics
duration: 8min
completed: 2026-06-22
---

# Phase 4 Plan 5: Build Verification + CI Guards Summary

**Publish-ready PyPI package verified: `uv build` produces wheel + sdist with `py.typed`, `twine check` passes, and shell-based CI guards keep `homeassistant.*` imports out of `src/` and `tests/`.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-06-22T12:30:00Z
- **Completed:** 2026-06-22T12:38:00Z
- **Tasks:** 1 (1 of 1 auto)
- **Files modified:** 5

## Accomplishments

- `uv build` exits 0, producing `dist/aionlslivetiming-0.1.0-py3-none-any.whl` + `dist/aionlslivetiming-0.1.0.tar.gz`
- Wheel contains `aionlslivetiming/py.typed` (PEP 561 marker, verified by `python -m zipfile -l`)
- `python -m twine check dist/*` exits 0 (both wheel and sdist PASSED)
- `bash scripts/check_no_ha_imports.sh` exits 0 (zero real HA import statements)
- 22/22 new tests in `tests/test_build.py` pass; full suite still 361 tests passing
- `pyproject.toml` `[project]` metadata covers all 9 PyPA fields (D-28)

## Task Commits

1. **Task 1: Verify build + metadata + create CI scripts (D-26..D-30)** - `26bcc71` (feat)

## Files Created/Modified

- `scripts/build.sh` - one-shot `uv build && uv run python -m twine check dist/*` wrapper
- `scripts/check_no_ha_imports.sh` - CI guard, regex-anchored to match real import statements only
- `tests/test_build.py` - 22 tests (parametrized metadata fields + script executability + .gitignore entries + uv build + wheel contents + twine check)
- `pyproject.toml` - added `twine>=6.0` to `[project.optional-dependencies].dev`
- `.gitignore` - added `site/` for mkdocs build output

## Decisions Made

- **Line-anchored regex for HA guard:** The plan's shell template uses substring grep which would false-positive on legitimate test docstrings/comments mentioning "homeassistant". Rewrote the regex to match only `^\s*(import homeassistant\b|from homeassistant(.\w+)?\s+import\b)`, mirroring the Python-level concern (D-30 is about import statements, not mentions). Verified by injecting a fake `import homeassistant` into a test file — the script fails with exit 1 as expected.
- **`uv run` wrapper for twine:** The plan template uses `python -m twine` which assumes a system-installed twine. Since `twine` is a dev-dep (`[project.optional-dependencies].dev`), `build.sh` uses `uv run python -m twine` so it works from a fresh `uv sync --extra dev` without requiring a global twine install.
- **Glob `.whl + .tar.gz` instead of `iterdir`:** During `test_twine_check_passes`, `uv build --out-dir <existing_tmp_dir>` copies repo files (`.gitignore`) alongside the wheel/sdist. Switching to glob-based artifact selection avoids the spurious `InvalidDistribution: Unknown distribution format: '.gitignore'` failure.
- **`uv build --out-dir` (not `--outdir`):** The plan's tests use `uv build --outdir`, which is the wrong flag in uv 0.10.x. Correct flag is `--out-dir`. Auto-fixed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `uv build --outdir` wrong flag in tests**
- **Found during:** Task 1 (`test_uv_build_produces_wheel_and_sdist`)
- **Issue:** Plan template passes `--outdir` to `uv build`; correct flag in uv 0.10.x is `--out-dir`. Test failed with `error: unexpected argument '--outdir' found`.
- **Fix:** Replaced `--outdir` with `--out-dir` in three test functions.
- **Files modified:** `tests/test_build.py`
- **Verification:** `uv build --out-dir <tmp>` now exits 0 in all three tests.
- **Committed in:** `26bcc71`

**2. [Rule 1 - Bug] Fixed shell script false positives on test docstrings/comments**
- **Found during:** Task 1 (`test_check_no_ha_imports_script_exits_zero`)
- **Issue:** Plan's shell template uses `grep -rn 'homeassistant' src/ tests/`. This matches the substring inside test docstrings (`tests/test_smoke.py:8` says "contains no homeassistant.* imports (D-11)") and identifier names (`test_no_homeassistant_imports`). The script failed with exit 1 on a clean repo because D-30 tests legitimately *mention* HA in their docstrings.
- **Fix:** Rewrote the shell script to grep with a line-anchored regex that matches only actual Python import statements: `^\s*(import homeassistant\b|from homeassistant(\.\w+)?\s+import\b)`. This mirrors the AST-level concern.
- **Files modified:** `scripts/check_no_ha_imports.sh`
- **Verification:** (a) `bash scripts/check_no_ha_imports.sh` exits 0 on clean repo. (b) Injecting `import homeassistant` into `tests/test_smoke.py` causes exit 1 with the offending line shown — both negative and positive paths verified.
- **Committed in:** `26bcc71`

**3. [Rule 1 - Bug] Fixed `python -m twine` failing on system python without twine**
- **Found during:** Task 1 (`bash scripts/build.sh` end-to-end check)
- **Issue:** Plan template uses `python -m twine check dist/*`. On a fresh machine where `twine` is installed only in the `uv` venv (per D-26: "twine is a dev-only check tool"), system `/usr/bin/python` has no twine module. The check silently fails and `build.sh` exits 0 anyway, giving a false sense of success.
- **Fix:** Changed `build.sh` to `uv run python -m twine check dist/*` so it uses the venv-installed twine.
- **Files modified:** `scripts/build.sh`
- **Verification:** `bash scripts/build.sh` now correctly invokes twine in the venv; both wheel and sdist show `PASSED`.
- **Committed in:** `26bcc71`

**4. [Rule 1 - Bug] Fixed `iterdir()` picking up non-artifact files in `test_twine_check_passes`**
- **Found during:** Task 1 (`test_twine_check_passes`)
- **Issue:** Plan's test iterates `build_dir.iterdir()` to find artifacts to pass to `twine check`. When `uv build --out-dir` is given an existing directory, it may copy repo files (like `.gitignore`) alongside the wheel + sdist. twine then errors with `InvalidDistribution: Unknown distribution format: '.gitignore'`.
- **Fix:** Replaced `sorted(build_dir.iterdir())` with `sorted(list(build_dir.glob("*.whl")) + list(build_dir.glob("*.tar.gz")))` to glob specifically for distribution artifacts.
- **Files modified:** `tests/test_build.py`
- **Verification:** `test_twine_check_passes` now exits 0 with both wheel and sdist `PASSED`.
- **Committed in:** `26bcc71`

**5. [Rule 3 - Blocking] chmod +x scripts (executable bit not set in prior session)**
- **Found during:** Task 1 (`test_check_no_ha_imports_script_executable`)
- **Issue:** Prior session left both scripts with mode 644 (no exec bit). `test_<script>_executable` failed on both.
- **Fix:** `chmod +x scripts/build.sh scripts/check_no_ha_imports.sh` → 755.
- **Files modified:** `scripts/build.sh`, `scripts/check_no_ha_imports.sh`
- **Verification:** `stat -c '%a'` shows 755 for both; both executable-bit tests pass.
- **Committed in:** `26bcc71`

---

**Total deviations:** 5 auto-fixed (4 bugs, 1 blocking)
**Impact on plan:** All deviations were bug fixes against the prior session's incomplete work + plan-template mistakes (wrong flag, false-positive shell regex, wrong python, wrong iterdir). No scope creep. The plan's stated deliverables (build.sh, check_no_ha_imports.sh, test_build.py with the listed test cases, .gitignore, pyproject.toml twine dep) are all present and correct.

## Issues Encountered

- `uv sync --extra dev` was needed before `twine` could be imported (the `pyproject.toml` change alone isn't enough — the venv needs to install it). Resolved automatically; no manual action required.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 4 is fully closed:

- DIST-01 (publish-ready): ✅ `uv build` produces valid wheel + sdist, `twine check` passes, `py.typed` is in the wheel
- DIST-04 (zero HA imports in core): ✅ CI guard in place, automated test enforces it

The first PyPI publish is a manual event outside this workflow per D-29. The `scripts/build.sh` + `scripts/check_no_ha_imports.sh` pair is the local sanity check; both exit 0 on this repo as of `26bcc71`.

---
*Phase: 04-client-distribution*
*Completed: 2026-06-22*