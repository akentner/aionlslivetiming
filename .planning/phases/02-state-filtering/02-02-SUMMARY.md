---
phase: 02-state-filtering
plan: 02
subsystem: state
tags: [filter, query-dsl, builder-pattern, pydantic, and-composition]

# Dependency graph
requires:
  - phase: 02-state-filtering
    plan: 01
    provides: "RaceState facade with .cars dict + .stats_best_sectors + per-car CarState pydantic models (class_name, starting_no, driver, position, laps_completed, sector_bests)"
provides:
  - "Filter DSL over RaceState — 6 composable dimensions with AND semantics"
  - "FILT-01..07 satisfied: by_class, by_starting_no, by_driver (case-insensitive substring), by_position (inclusive, unknown-position opt-in), by_lap (inclusive), sector_time_lt (strict less-than)"
  - "RaceState.filter() factory + convenience pass-throughs: cars_by_class, cars_by_starting_no, top"
  - "Filter.starting_nos() terminal — returns int list for Discord bot / dashboard needs"
  - "List return type (not generator) — easier to test and serialize (ARCHITECTURE.md line 161)"
affects:
  - "02-03 (persistence): state.filter() shape is the read API; persistence will serialize the same CarState list shape"
  - "03 (transport): Live / Replay wrappers expose state.filter() to consumers"
  - "04 (client + distribution): Client ties state.filter() into the public Discord bot / HA sensor / dashboard shape"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Builder pattern with method chaining — state.filter().by_class('SP9').top(5).cars()"
    - "AND across dimensions, OR within driver substrings (multi-substring driver filter)"
    - "Set semantics for by_class / by_starting_no (idempotent — calling twice has no extra effect)"
    - "List semantics for by_driver (accumulates; matches ANY substring)"
    - "Single-value setters for by_position / by_lap / sector_time_lt / top (last-write-wins)"
    - "Defensive copies: state.cars already defensive-copies the dict; Filter.cars builds a fresh list each call"
    - "Local import inside RaceState.filter() to keep the dependency direction clean (state.filter is a runtime import, not a top-level one)"
    - "Frozen=False constraint not relaxed: Filter itself is mutable per-query state — that's intentional, each call to state.filter() returns a fresh Filter"

key-files:
  created:
    - src/aionlslivetiming/state/filter.py
    - tests/test_state_filters.py
  modified:
    - src/aionlslivetiming/state/race_state.py
    - src/aionlslivetiming/state/__init__.py
    - src/aionlslivetiming/__init__.py

key-decisions:
  - "FILT-01..07 design decisions (D-FILT-1..7) honored: builder pattern + method-on-cache both available"
  - "Driver filter is case-insensitive substring (D-FILT-2) — OR across substrings"
  - "Position filter excludes unknown (position=None) by default; include_unknown_position() opt-in (D-FILT-3)"
  - "Lap filter is inclusive on laps_completed (D-FILT-4)"
  - "Sector threshold is STRICT less-than (D-FILT-5) — sector 1 of Nordschleife is ~60s in dry, so 35s default is sensible for testing"
  - "Filter.cars() returns list, not generator (D-FILT-6, ARCHITECTURE.md line 161)"
  - "AND composition across all dimensions (D-FILT-7); methods are idempotent"
  - "Test expectations corrected during RED->GREEN: 'er' matches Mueller/Weber/Bauer/Fischer (4 of 6) — Klein has no 'er' substring. test_by_lap test renamed/repurposed to exercise by_lap with a real-position car (unknown-position is filtered out by the default position filter)"
  - "Filter is mutable per-query — state.filter() returns a fresh instance every call (asserted by test_filter_returns_new_instance_each_call). Mutation isolation comes from object identity, not locking"

patterns-established:
  - "Pattern 1: Filter DSL builders compose via AND — each method narrows the working set, no method ORs dimensions"
  - "Pattern 2: Both .filter().by_class().cars() (builder) AND state.cars_by_class() (method-on-cache) shapes are public — consumer chooses"
  - "Pattern 3: Test files declare their own fixture (make_race_state in test_state_filters.py) — keeps each test file self-contained, matches the Phase 1 convention"
  - "Pattern 4: Test files inject test-only data directly into _cars (private attribute) with an _cars mutator — necessary for sector_bests which InitialStateMessage doesn't carry on cars"

requirements-completed: [FILT-01, FILT-02, FILT-03, FILT-04, FILT-05, FILT-06, FILT-07]

# Metrics
duration: ~6min 20sec
completed: 2026-06-20
---

# Phase 02 Plan 02: Filter DSL — 6 Dimensions + AND Composition

**Composable query object over `RaceState.cars` that exposes six independent filter dimensions (`by_class` / `by_starting_no` / `by_driver` / `by_position` / `by_lap` / `sector_time_lt`) which AND-combine into one query result, plus convenience pass-throughs on `RaceState` for the FastF1-style method-on-cache shape.**

## Performance

- **Duration:** ~6 min 20 sec
- **Started:** 2026-06-20T17:34:07Z
- **Completed:** 2026-06-20T17:40:24Z
- **Tasks:** 1 (TDD: RED + GREEN, with one REFACTOR-style commit to fix `__all__` sort)
- **Files modified:** 5 (2 created, 3 modified)
- **Tests added:** 40 (all green)

## Accomplishments

- **Filter class in `state/filter.py`** — builder-pattern query object. Each method narrows the working set; `.cars()` materialises the result as a list of `CarState` ordered by position (None last)
- **6 filter dimensions implemented (FILT-01..06)**:
  - `by_class(name)` — set union semantics, idempotent
  - `by_starting_no(int | Iterable[int])` — accepts single int or iterable, set union
  - `by_driver(substring)` — case-insensitive substring, OR across substrings
  - `by_position(min=, max=)` — inclusive bounds, unknown-position excluded by default
  - `by_lap(min=, max=)` — inclusive bounds on `laps_completed`
  - `sector_time_lt(sector=, value_ms=)` — strict less-than on per-car sector bests
- **AND composition (FILT-07)**: 4-dimension AND test (`by_class("SP9").by_position(max=2).by_lap(min=28).sector_time_lt(...)`) returns the expected single car
- **Convenience pass-throughs**: `state.filter()`, `state.cars_by_class()`, `state.cars_by_starting_no()`, `state.top(n)` — both builder pattern and method-on-cache work
- **Public API**: `from aionlslivetiming import Filter, RaceState` — Filter is part of the top-level export surface
- **40 new tests** organized by dimension + composition + convenience + edge cases
- **Coverage at 94.50%** (filter.py at 97%, state/ at 97%) — well above the 80% DIST-06 gate
- **mypy --strict + ruff clean** across the full src/ + the new test files
- **160 tests pass total** (120 from Phase 1 + Plan 01 + 40 new from this plan)

## Task Commits

TDD execution with 3 atomic commits:

1. **RED: Failing tests** — `f7b2262` (test)
   - 40 new test cases in `tests/test_state_filters.py`
   - Confirmed `ImportError: cannot import name 'Filter' from 'aionlslivetiming'`
2. **GREEN: Implementation** — `c3627b7` (feat)
   - `state/filter.py` (Filter class)
   - `state/race_state.py` extended with `filter()`, `cars_by_class()`, `cars_by_starting_no()`, `top()`
   - `state/__init__.py` re-exports Filter
   - Top-level `__init__.py` re-exports Filter
   - All 40 filter tests + 120 existing = 160 green
   - Lint cleanups: TC003 (Iterable → TYPE_CHECKING), SIM103 (negated returns), RUF100 (unused noqa), E501 (docstring wrap), RUF022 (`__all__` sort), F821 (Filter forward ref)

## Files Created/Modified

### Created

- `src/aionlslivetiming/state/filter.py` (178 lines) — Filter query object, all 6 dimensions, AND composition, list return type
- `tests/test_state_filters.py` (470 lines) — 40 tests covering all dimensions + AND composition + convenience pass-throughs + edge cases (empty state, unknown-position opt-in, boundary cases)

### Modified

- `src/aionlslivetiming/state/race_state.py` — added `Iterable` and `Filter` to TYPE_CHECKING imports; added `filter()` factory and `cars_by_class()` / `cars_by_starting_no()` / `top()` convenience pass-throughs
- `src/aionlslivetiming/state/__init__.py` — re-export Filter alongside CarState/Freshness/LapRecord/RaceState/Source/TrackState
- `src/aionlslivetiming/__init__.py` — re-export Filter at the top level so consumers can `from aionlslivetiming import Filter`

## Decisions Made

- **Filter is mutable per-query** — `state.filter()` returns a fresh instance every call. Object identity provides isolation between queries; no locking needed under the same single-writer contract that RaceState uses. Asserted by `test_filter_returns_new_instance_each_call`
- **Local import in `RaceState.filter()`** — `from aionlslivetiming.state.filter import Filter` is inside the method, not at module top level. This keeps the dependency direction clean: `filter.py` imports `RaceState` under TYPE_CHECKING only, so a top-level import would be circular
- **OR semantics for driver substrings** — calling `by_driver("Muel").by_driver("Schm")` keeps cars that match EITHER substring (both Mueller and Schmidt). The filter narrows across dimensions (AND) but expands within the driver dimension (OR-of-substrings)
- **Set union for `by_class` and `by_starting_no`** — idempotent, calling twice with the same value has no extra effect (set semantics). `by_class("SP9").by_class("SP9")` returns the same 3 SP9 cars
- **`__all__` sorted alphabetically** — ruff RUF022 enforces it. `["Filter", "Freshness", "RaceState", "Source", "__version__", "get_logger"]` (dunder conventionally sorts last by the rule)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test] Corrected test expectations for `test_by_driver_substring_partial`**
- **Found during:** Task 1 RED→GREEN transition
- **Issue:** Plan's spec said substring 'er' matches 4 of 6 cars (Weber/Bauer/Fischer/Klein). Actually 'Mueller' also contains 'er' (the end), so 5 of 6 match. Plan then also said Klein matches, but Klein has no 'er' substring — only 4 actually match (Mueller/Weber/Bauer/Fischer)
- **Fix:** Updated test to expect `[7, 22, 44, 55]` (Mueller, Weber, Bauer, Fischer) and corrected docstring
- **Files modified:** `tests/test_state_filters.py`
- **Verification:** Test now passes; `by_driver("er")` correctly returns 4 cars (Mueller/Weber/Bauer/Fischer)
- **Committed in:** `c3627b7` (initial GREEN)

**2. [Rule 1 - Test] Repurposed `test_by_lap_excludes_unknown_laps` to `test_by_lap_filters_by_laps_completed_only`**
- **Found during:** Task 1 RED→GREEN transition
- **Issue:** Test name and intent were misleading. The test injected a car with `position=None` and expected `by_lap(min=0)` to include it, but the default position filter (which runs unconditionally, not just when `by_position` is called) excludes unknown-position cars. The car was filtered out before by_lap got a chance to act
- **Fix:** Renamed test, gave the injected car a real position (7), and asserted `by_lap(min=10)` includes it. Test now exercises the dimension in isolation
- **Files modified:** `tests/test_state_filters.py`
- **Verification:** Test now passes; by_lap dimension correctly filters on `laps_completed >= min` regardless of other dimensions
- **Committed in:** `c3627b7`

**3. [Rule 1 - Lint] Moved `Iterable` to TYPE_CHECKING block (TC003)**
- **Found during:** Task 1 (ruff check after GREEN)
- **Issue:** Plan's reference code imports `Iterable` at module top level in both `filter.py` and `race_state.py`, but it's only used in type annotations
- **Fix:** Moved both `Iterable` imports into `if TYPE_CHECKING:` blocks
- **Files modified:** `src/aionlslivetiming/state/filter.py`, `src/aionlslivetiming/state/race_state.py`
- **Verification:** `ruff check` clean, mypy --strict still happy
- **Committed in:** `c3627b7`

**4. [Rule 1 - Lint] Inverted return conditions (SIM103)**
- **Found during:** Task 1 (ruff check after GREEN)
- **Issue:** Plan's reference `pos_match` and `lap_match` helpers had a 3-line shape (early return False, early return False, return True) that ruff's SIM103 wants collapsed to a single return
- **Fix:** Changed the second early return to `return not (max is not None and c.position > max)` — single-statement form
- **Files modified:** `src/aionlslivetiming/state/filter.py`
- **Verification:** `ruff check` clean, all tests still pass
- **Committed in:** `c3627b7`

**5. [Rule 1 - Lint] Removed unused `# noqa: SLF001` directives (RUF100)**
- **Found during:** Task 1 (ruff check after GREEN)
- **Issue:** Test file had 6 `# noqa: SLF001` comments silencing the private-attribute access lint, but SLF001 is not in the project's selected rules — so the noqa directives were unused noise
- **Fix:** Removed all 6 noqa comments
- **Files modified:** `tests/test_state_filters.py`
- **Verification:** `ruff check` clean
- **Committed in:** `c3627b7`

**6. [Rule 1 - Lint] Wrapped E501 docstring line and sorted `__all__` (RUF022)**
- **Found during:** Task 1 (ruff check after GREEN)
- **Issue:** `RaceState.filter()` docstring was 101 chars (E501, line too long); top-level `__all__` was not alphabetically sorted (RUF022)
- **Fix:** Wrapped the docstring on `:class:`~aionlslivetiming.state.filter.Filter`` so each line is < 100 chars; sorted `__all__` to alphabetical order (dunder conventionally sorts last per the rule)
- **Files modified:** `src/aionlslivetiming/state/race_state.py`, `src/aionlslivetiming/__init__.py`
- **Verification:** `ruff check` clean
- **Committed in:** `c3627b7`

---

**Total deviations:** 6 auto-fixed (3 lint cleanups + 2 test corrections + 1 docstring/`__all__` cleanup)
**Impact on plan:** All auto-fixes were cosmetic / correctness-of-tests. The Filter implementation matches the plan's reference code exactly in behaviour. The two test corrections were genuine errors in the plan's expected values (off-by-one substring match count, misleading test name for `by_lap`).

## Issues Encountered

None of substance. The plan's reference code translated directly to a working implementation; only the six auto-fixes above were needed. Coverage, mypy, and the full test suite passed on the first GREEN run (after test expectation corrections).

## User Setup Required

None — no external service configuration required. This plan completes the public read API for `RaceState` (filter DSL on top of the existing reducer). Phase 3 will connect this to the WebSocket transport; consumers (Discord bots, HA sensors) can already use `state.filter().by_class("SP9").top(5).cars()` against any state populated by `state.apply(msg)`.

## Next Phase Readiness

**Ready for Plan 02-03 (persistence)**: `state.filter().cars()` returns the canonical list of `CarState` for any dimension combination — Plan 03 will serialize the same shape to JSON via `CarState.model_dump()`.

**Ready for Phase 3 (transport)**: Live / Replay wrappers feed messages into `state.apply()`; consumers then read via `state.filter().by_class("SP9").cars()` (builder) or `state.cars_by_class("SP9")` (method-on-cache). Both shapes are public.

**Open design questions (unchanged)**: The Phase 3 design questions (Azure App Service idle timeout, `websockets` ping tuning, `LTS_NOT_FOUND` three-state policy) still need a `/gsd-research-phase` spike before implementation. Capture a real JSONL during a live test session before declaring Phase 3 done.

## Self-Check: PASSED

- All 5 files exist (2 created + 3 modified)
- Both commits exist: `f7b2262` (RED: failing tests) and `c3627b7` (GREEN: implementation)
- `uv run pytest` reports **160 passed** at **94.50% coverage** (80% gate met)
- `uv run mypy --strict src/aionlslivetiming/` reports **Success: no issues found in 33 source files**
- `uv run ruff check src/aionlslivetiming/ tests/` reports **All checks passed!**
- Manual smoke test from plan verification block passes (with 3 SP9 cars in fixture):
  ```python
  assert len(s.filter().by_class("SP9").cars()) == 3
  assert [c.starting_no for c in s.filter().by_class("SP9").top(2).cars()] == [7, 11]
  assert len(s.filter().sector_time_lt(sector=1, value_ms=33000).cars()) == 1
  ```

---
*Phase: 02-state-filtering*
*Completed: 2026-06-20*
