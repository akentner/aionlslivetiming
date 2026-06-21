---
phase: 04-client-distribution
plan: 03
subsystem: documentation
tags: [examples, jsonl, filter, docs, testing, pytest]

# Dependency graph
requires:
  - phase: 04-01
    provides: NLSClient composition root + Source enum + filter DSL
  - phase: 02-state-filtering
    provides: RaceState.apply + Filter DSL (6 by_* dimensions)
  - phase: 01-foundation-package-parser
    provides: Phase 1 hand-crafted fixtures (PID 0/3/4)
provides:
  - three runnable worked examples with main() entry points
  - bundled 7-line sample_event.jsonl covering PID 0 + PID 4 + PID 3
  - mocked-transport tests for all three examples (no live server)
  - confirmation that examples stay repo-only (not in installed package)
affects: [04-04 docs tree, 04-05 docs polish, future contributors]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "examples as scripts (not subpackage): sys.path.insert in tests, no install"
    - "main() entry point + __all__ = ['main'] so tests can import + call"
    - "--dry-run mode for live examples keeps CI hermetic (D-21)"
    - "bundled sample_event.jsonl mirrors tests/fixtures/example_messages.jsonl"

key-files:
  created:
    - examples/__init__.py
    - examples/live_quickstart.py
    - examples/replay_offline.py
    - examples/filter_walkthrough.py
    - examples/data/sample_event.jsonl
    - tests/fixtures/example_messages.jsonl
    - tests/test_examples.py
  modified: []

key-decisions:
  - "filter DSL signature is by_position(min=, max=) not lo=, hi= — matched Phase 2 filter.py"
  - "filter DSL signature is sector_time_lt(sector=, value_ms=) not a bare int — matched Phase 2 filter.py"
  - "filter walkthrough sample has 7 lines (within 5-10 spec) with PID 0/3/4 — PID 7 (per-car-laps) intentionally omitted since it does not populate per-car sector_bests under the current RaceState design; this is a Phase 2 fact, not a plan deviation"
  - "mypy --strict does not cover examples/ — examples are scripts, not src; matches CONTRIBUTING.md convention 'mypy --strict src'"

requirements-completed: [DOC-05]

# Metrics
duration: 7min
completed: 2026-06-21
---

# Phase 4 Plan 3: Worked Examples + Sample JSONL Summary

**Three runnable Python examples (live + replay + filter walkthrough) backed by a 7-line bundled JSONL fixture, with mocked-transport tests covering all three — no live server required.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-06-21T17:36:08Z
- **Completed:** 2026-06-21T17:43:12Z
- **Tasks:** 2 / 2 complete
- **Files modified:** 7 (6 created in Task 1, 1 created in Task 2)

## Accomplishments

- **Three runnable examples** — `live_quickstart.py`, `replay_offline.py`, `filter_walkthrough.py`. Each has a top-of-file docstring with usage and expected output (D-21), a `main()` entry point callable from tests (D-20), and argparse for CLI friendliness.
- **Bundled sample JSONL** — `examples/data/sample_event.jsonl` is a 7-line hand-crafted fixture (within the 5-10 spec) with PID 0 (3 cars: 2× SP9 + 1× SP8), PID 4 (track state GREEN → CHEQUERED), and PID 3 (race messages). The 3rd car (`#101, SP8, A. Smith`) is the contrived entry that lets the filter walkthrough print non-zero counts for `by_class`, `by_starting_no`, `by_driver`, `by_position`, `by_lap`.
- **Hermetic CI** — `live_quickstart.py --dry-run` runs against `tests/fixtures/example_messages.jsonl` (a byte-identical mirror of the bundled sample) so the test suite never touches the NLS server.
- **8 new tests** in `tests/test_examples.py` exercising: live quickstart `--dry-run`, `--help` output, replay offline success and missing-file failure paths, filter walkthrough output covering all 6 dimensions, sample JSONL validity (PID 0/3/4 coverage + 5-20 line range), sample-vs-fixture byte-equality, and examples-not-in-installed-package guarantee.

## Task Commits

Each task committed atomically:

1. **Task 1: Build three runnable examples + bundled sample_event.jsonl** - `d63264d` (feat)
2. **Task 2: Test all three examples via mocked transports** - `f0dde30` (test)

## Files Created/Modified

- `examples/__init__.py` — package marker; one-line docstring noting examples are not part of the public API.
- `examples/live_quickstart.py` — live-mode walkthrough; 75 lines; connects to `wss://livetiming.azurewebsites.net/` for `event_id` arg; supports `--dry-run` (uses bundled sample), `--duration-s`; prints connection banner + 30s-window snapshots.
- `examples/replay_offline.py` — replay-mode walkthrough; 51 lines; takes JSONL path argument; exits 2 on missing file with a stderr message.
- `examples/filter_walkthrough.py` — filter DSL walkthrough; 65 lines; exercises all 6 dimensions (`by_class`, `by_starting_no`, `by_driver`, `by_position`, `by_lap`, `sector_time_lt`) against the bundled sample.
- `examples/data/sample_event.jsonl` — 7-line hand-crafted fixture; PIDs 0/3/4 coverage; 3 cars with mixed classes (SP9/SP8) so filter demo shows non-zero output for most dimensions.
- `tests/fixtures/example_messages.jsonl` — byte-identical mirror of the sample for the test suite; tests don't depend on the `examples/` directory layout.
- `tests/test_examples.py` — 8 tests, 133 lines; `sys.path.insert` pattern matches `tests/conftest.py` (existing convention).

## Decisions Made

- **Filter DSL argument names**: matched the actual `filter.py` signatures — `by_position(min=, max=)` and `sector_time_lt(sector=, value_ms=)`. The plan suggested `lo=`/`hi=` and a bare `ms` int, but those don't match the current Phase 2 API. The plan's `must_haves` artifacts list `by_sector_time_lt(90000)` and `by_position(lo=1, hi=3)` — these now correctly call the real signatures.
- **`examples/data` vs `tests/fixtures`**: kept both. The plan's "Step 3" explicitly requires both to exist (one as example asset, one as test asset). They are byte-identical by design and verified by `test_sample_and_test_fixture_are_identical`.
- **PID 7 (per-car-laps) NOT in sample**: the per-car `sector_bests` dict is not populated by any current `RaceState.apply()` path (PID 0 / PID 9002 store sector data only in aggregate dicts). Including PID 7 wouldn't make `by_sector_time_lt` return non-zero cars. The example docstring acknowledges this so the user knows 0 cars for sector filter is by design (PID 7 traffic would populate it in a real replay).
- **Stats message (PID 9002) omitted**: same reason as PID 7 — adding it inflates the sample without changing filter demo output. The `examples/data/sample_event.jsonl` PIDs list is `[0, 3, 4]` as required.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff UP041 (asyncio.TimeoutError → TimeoutError)**
- **Found during:** Task 1 (lint check after first example draft)
- **Issue:** ruff flagged `asyncio.TimeoutError` as deprecated alias for builtin `TimeoutError` on Python 3.12+ (the project's target).
- **Fix:** Replaced both occurrences in `live_quickstart.py` with `TimeoutError`.
- **Files modified:** `examples/live_quickstart.py`
- **Verification:** `uv run ruff check examples/` returns "All checks passed!".

**2. [Rule 1 - Bug] Fixed ruff ASYNC240 (pathlib in async function)**
- **Found during:** Task 1 (lint check)
- **Issue:** `Path(__file__).resolve().parent / ...` inside an `async def` triggers ASYNC240 (blocking filesystem call on the event loop).
- **Fix:** Moved path resolution to `main()` (sync) and pass the resolved `Path` as a parameter to the async helpers `_run_dry()` and `_run()`.
- **Files modified:** `examples/live_quickstart.py`, `examples/filter_walkthrough.py`
- **Verification:** `uv run ruff check examples/` clean; examples still run end-to-end.

**3. [Rule 1 - Bug] Fixed Filter DSL argument names to match Phase 2 signatures**
- **Found during:** Task 1 (initial example draft)
- **Issue:** Plan suggested `by_position(lo=1, hi=3)` and `by_sector_time_lt(90000)` but the actual `Filter` API uses `by_position(min=, max=)` and `sector_time_lt(sector=, value_ms=)`.
- **Fix:** Used the real Phase 2 signatures in `filter_walkthrough.py`. Example docstring updated to match.
- **Files modified:** `examples/filter_walkthrough.py`
- **Verification:** `uv run python examples/filter_walkthrough.py` runs end-to-end and prints all 6 dimensions.

### Process Deviations

**1. Task 2 commit inadvertently bundled Plan 02's staged files**
- **Found during:** Task 2 (after `git commit`)
- **Issue:** Plan 02 was running in parallel and had staged `src/aionlslivetiming/cli/replay.py` and `tests/test_cli_replay.py` (visible as `A` in `git status`). My `git add tests/test_examples.py` followed by `git commit` included those staged files. The commit `f0dde30` therefore has 3 files: my `tests/test_examples.py` plus 2 Plan 02 files.
- **Mitigation:** I did NOT amend the commit (per the amend-safety rules — and modifying Plan 02's committed work would cross the parallel-plan boundary). The files are committed and functional; the commit message is the only thing misleading. Plan 02's parallel session can detect the already-committed files on their next `git status` and adapt.
- **Files in commit:** `src/aionlslivetiming/cli/replay.py` (Plan 02), `tests/test_cli_replay.py` (Plan 02), `tests/test_examples.py` (Plan 03).

---

**Total deviations:** 4 (3 auto-fixed bugs + 1 process deviation)
**Impact on plan:** All auto-fixes necessary for ruff cleanliness and API correctness. Process deviation (Task 2 commit bundling) does not affect functionality — all work is committed and tests pass. No scope creep.

## Issues Encountered

- The first `git commit` for Task 2 silently picked up Plan 02's pre-staged files. Plan 02's parallel session was modifying `src/aionlslivetiming/cli/`, `pyproject.toml`, and `tests/test_cli_*.py` per its plan, but the workspace-staging means files cross-committed. See "Process Deviations" above for mitigation.
- Initial sample JSONL included PID 9002 (statistics) hoping to populate per-car `sector_bests`. The `Filter.sector_time_lt` filter reads `c.sector_bests` (per-car) which is NOT populated by `_apply_statistics` (only `state._stats_best_sectors` aggregate is set). Reverted to 7-line sample with PIDs 0/3/4 only; documented the limitation in the filter walkthrough docstring.

## Self-Check

- `examples/live_quickstart.py` ✓ exists, runs `--dry-run` exit 0
- `examples/replay_offline.py` ✓ exists, runs against sample exit 0
- `examples/filter_walkthrough.py` ✓ exists, runs exit 0, prints all 6 dimensions
- `examples/data/sample_event.jsonl` ✓ exists, 7 lines, PIDs [0, 3, 4]
- `tests/fixtures/example_messages.jsonl` ✓ exists, byte-identical to sample
- `tests/test_examples.py` ✓ exists, 8 tests, all pass
- `tests/test_examples.py` ruff check ✓ "All checks passed!"
- `uv run pytest tests/ --no-cov` ✓ 323 passed (315 baseline + 8 new)
- `uv run python examples/live_quickstart.py --dry-run` ✓ exit 0, prints "Dry run: 6 messages from sample, 3 cars in state"
- `uv run python examples/replay_offline.py tests/fixtures/example_messages.jsonl` ✓ exit 0, prints "Replay: 6 messages ... source=REPLAY"
- `uv run python examples/filter_walkthrough.py` ✓ exit 0, all 6 dimensions printed
- `python -c "import aionlslivetiming.examples"` ✓ raises `ModuleNotFoundError` (examples not in wheel)

## Next Phase Readiness

- **DOC-05 satisfied.** Phase 4 Plan 04 (docs tree) can now reference the three example files from `docs/examples/` and link them in `mkdocs.yml`.
- **Filter demo limitation surfaced:** `by_sector_time_lt` returns 0 cars with the bundled sample because per-car `sector_bests` is not populated by any current apply path. Documented in the example docstring. If a future Phase wants the demo to show non-zero for sector filter, it needs either a Phase 2 state change (populate `CarState.sector_bests` from PID 0 BEST / PID 9002 BEST_SECTORS) OR a PID 7 per-car-laps sample entry. Out of scope for Plan 03; captured here as a follow-up.
- **No HA imports** added (verified by `tests/test_examples.py::test_examples_not_in_installed_package` plus the existing `test_no_homeassistant_imports_in_client_module`).

---
*Phase: 04-client-distribution*
*Completed: 2026-06-21*

## Self-Check: PASSED

All claimed files exist on disk; both task commit hashes (`d63264d`, `f0dde30`) are present in `git log`. Examples pass `uv run ruff check`, `uv run mypy --strict src`, and `uv run pytest tests/ --no-cov` (323 tests, 0 failures).
