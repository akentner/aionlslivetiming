---
phase: 02-state-filtering
plan: 01
subsystem: state
tags: [pydantic, reducer, cache, idempotency, freshness, source]

# Dependency graph
requires:
  - phase: 01-foundation-package-parser
    provides: "8 typed Message dataclasses (InitialStateMessage, TrackStateMessage, RaceMessage, PerCarLapsMessage, QualifyingMessage, StatisticsMessage, TimeSyncMessage, UnknownMessage) + SessionInfo/CarResult/BestSector/TimeOfDay"
provides:
  - "RaceState facade with idempotent apply(msg) for all 7 typed messages (TimeSync/Unknown are no-ops)"
  - "CarState / TrackState / LapRecord pydantic value models (extra=allow for schema tolerance)"
  - "Source (LIVE/REPLAY/IMPORTED) + Freshness (FRESH/STALE/RESYNCING) stdlib enums"
  - "Per-car lap drilldown via state.laps(starting_no, session=...) sorted by lap_no"
  - "standings() sorted by position (None last); clear() resets all sub-caches to RESYNCING"
  - "Single-writer contract — no locks, no asyncio (caller's task owns serialization)"
affects:
  - "02-02 (filters): reads state.cars / state.standings() / state.laps() to build Filter DSL"
  - "02-03 (persistence): reads RaceState shape to serialize to JSON / deserialize from JSON"
  - "03 (transport): Live / Replay / Recording wrappers feed messages into state.apply()"
  - "04 (client): Client ties transport → state → filter into the public API"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "D-02 enforced: events/ is stdlib dataclass (frozen+slots), state/ is pydantic (extra=allow)"
    - "D-03 enforced: state.apply never raises — malformed lap dicts are dropped, not raised"
    - "Boundary rule (ARCHITECTURE.md line 166): state/ imports only from events/, never from parser/ or transport/"
    - "Defensive copies: state.cars / state.stats_best_sectors return dict(self._x); state.messages returns the tuple directly (already immutable)"
    - "Idempotency strategies vary per type: InitialStateMessage resets cars dict; TrackStateMessage replaces TrackState instance; RaceMessage dedupes on (text, category, starting_no, session) key; PerCarLapsMessage keyed by (session, starting_no, lap_no) last-write-wins; QualifyingMessage replaces results tuple; StatisticsMessage keeps min per (starting_no, sector) for sector_bests"
    - "PID 0 semantics: full reset of cars dict (matches server's 'fresh snapshot' meaning per ARCHITECTURE.md line 226)"

key-files:
  created:
    - src/aionlslivetiming/state/__init__.py
    - src/aionlslivetiming/state/enums.py
    - src/aionlslivetiming/state/car.py
    - src/aionlslivetiming/state/track.py
    - src/aionlslivetiming/state/lap.py
    - src/aionlslivetiming/state/race_state.py
    - tests/test_state_apply.py
    - tests/test_state_idempotency.py
    - tests/test_state_freshness.py
  modified:
    - src/aionlslivetiming/__init__.py
    - pyproject.toml

key-decisions:
  - "CarState is NOT frozen (frozen=False) because RaceState mutates sector_bests in-place when a new best arrives; single-writer access is the caller's responsibility"
  - "LapRecord and TrackState ARE frozen — once a lap is recorded or a PID 4 frame is parsed, the value is immutable; new data replaces via key, not mutation"
  - "TimeOfDay dataclasses from TrackStateMessage are flattened to tod_ms/end_time_ms ints in TrackState so consumers don't need to import from events/"
  - "RaceMessage dedupe key is (text, category, starting_no, session) — chosen because the server can replay or duplicate identical frames during high-frequency updates per PITFALLS.md #3"
  - "PerCarLapsMessage is keyed by (session, starting_no, lap_no) for last-write-wins; missing 'lap' or 'time' fields drop the lap (D-03), int coercion failures also drop"
  - "state.cars returns dict(self._cars) (defensive copy) so consumers cannot mutate internal state via the property"
  - "freshness default is RESYNCING (not FRESH) so a fresh RaceState() is honest about being empty"
  - "Public re-exports: RaceState/Source/Freshness from aionlslivetiming.__init__; full state surface from aionlslivetiming.state.__init__"

patterns-established:
  - "Pattern 1: state subpackage mirrors the events/ shape — one file per value type, race_state.py is the facade, __init__.py re-exports the public surface"
  - "Pattern 2: tests are organized by behavior (apply/idempotency/freshness) not by module — easier to read what is verified"
  - "Pattern 3: state_to_dict() helper in test_state_apply.py provides structural snapshots for idempotency assertions across the full pipeline"
  - "Pattern 4: helper-message constructors (_initial(), _r1_initial()) live in the test file that uses them — keeps each test self-contained"

requirements-completed: [STATE-01, STATE-02, STATE-03, STATE-04, STATE-05]

# Metrics
duration: ~6min
completed: 2026-06-20
---

# Phase 02 Plan 01: State Module — RaceState Reducer

**Idempotent in-memory race cache that turns the 7 typed Messages (TimeSync + Unknown are no-ops) into a queryable, freshness-tracked state — pydantic value models + stdlib Source/Freshness enums + single-writer apply() contract.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-20T17:27:56Z
- **Completed:** 2026-06-20T17:34:00Z
- **Tasks:** 1 (TDD: RED commit + GREEN commit)
- **Files modified:** 11 (6 created, 2 modified in src + tests, 1 pyproject.toml, 1 top-level __init__, 1 mypy re-verify)

## Accomplishments

- **RaceState reducer** with idempotent `apply(msg)` that dispatches via `isinstance` across all 7 typed messages, with TimeSync/Unknown as forward-compat no-ops (D-05)
- **Per-type idempotency strategies**: PID 0 resets cars dict; PID 4 replaces TrackState instance; PID 3 dedupes on `(text, category, starting_no, session)`; PID 7 keyed by `(session, starting_no, lap_no)`; PID 501 replaces results tuple; PID 9002 keeps min per sector
- **D-03 (never-raise) contract**: malformed lap dicts (missing `lap` or `time`, non-integer values) are dropped silently; `apply()` returns `None`
- **D-02 enforced**: events/ stays stdlib dataclass (frozen+slots), state/ is pydantic with `extra="allow"` for schema tolerance
- **27 new tests** organized by behavior (apply / idempotency / freshness) — 12 per-message-type, 7 idempotency, 7 freshness/source/clear, plus 1 helper
- **Coverage on state/ at 99%** (race_state.py 142 stmts, 2 missing on property accessors for `ver` / `export_id` that no current test path hits) — well above 80% DIST-06 gate
- **Total suite: 120 passed** (93 Phase 1 + 27 new state tests) at **94.33% overall coverage**
- **mypy --strict + ruff clean** across the full src/ + the new test files

## Task Commits

TDD execution produced 2 atomic commits:

1. **RED: Failing tests** - `de19b3e` (test)
   - 27 new test cases across 3 files (test_state_apply.py / test_state_idempotency.py / test_state_freshness.py)
   - Confirmed `ModuleNotFoundError: No module named 'aionlslivetiming.state'` to prove tests are real
2. **GREEN: Implementation** - `a64b7fd` (feat)
   - 6 new state/ source files
   - Top-level `__init__.py` re-export
   - `pyproject.toml` coverage addopts extended to include state module
   - Lint fixes: removed unused `TimeSyncMessage`/`UnknownMessage` imports from race_state.py (intentional — they are no-op'd, not dispatched), unused `TimeOfDay` from test_state_freshness.py, E501 long-line wrap in test_state_apply.py
   - All 27 state tests green, full suite 120 passed, mypy --strict + ruff clean

## Files Created/Modified

### Created

- `src/aionlslivetiming/state/__init__.py` (16 lines) — re-exports public surface: CarState, Freshness, LapRecord, RaceState, Source, TrackState
- `src/aionlslivetiming/state/enums.py` (44 lines) — Source (LIVE/REPLAY/IMPORTED) + Freshness (FRESH/STALE/RESYNCING) stdlib enums
- `src/aionlslivetiming/state/lap.py` (29 lines) — LapRecord pydantic (frozen, extra="allow") — one PID 7 lap with lap_no/time_ms/s1_ms/s2_ms/s3_ms
- `src/aionlslivetiming/state/car.py` (28 lines) — CarState pydantic (frozen=False) — one car with starting_no/position/class_name/driver/laps_completed/total_time_ms/gap_to_leader_ms/best_lap_ms/sector_bests
- `src/aionlslivetiming/state/track.py` (22 lines) — TrackState pydantic (frozen) — one PID 4 frame flattened to tod_ms/end_time_ms
- `src/aionlslivetiming/state/race_state.py` (190 lines) — RaceState facade: `apply()` dispatches via isinstance, `set_source()`, `clear()`, `laps()`, `standings()`, plus read-side properties
- `tests/test_state_apply.py` (250 lines) — 12 per-message-type apply() tests + `state_to_dict()` helper
- `tests/test_state_idempotency.py` (130 lines) — 7 idempotency tests including a full-pipeline snapshot test
- `tests/test_state_freshness.py` (110 lines) — 7 freshness/source/clear tests

### Modified

- `src/aionlslivetiming/__init__.py` — re-export `RaceState`, `Source`, `Freshness` for the public API
- `pyproject.toml` — extend `addopts` to include `--cov=aionlslivetiming.state`

## Decisions Made

- **CarState is not frozen** because the reducer mutates `sector_bests` in-place when a new best arrives; single-writer access is the consumer's contract (ARCHITECTURE.md line 168)
- **LapRecord and TrackState ARE frozen** — once a lap or a PID 4 frame is parsed, the value is immutable; new data replaces via key, not mutation. Matches the immutability of the source `Message` dataclasses
- **TimeOfDay is flattened to int** in TrackState so consumers don't need to import from `aionlslivetiming.events` to read the cache — keeps the public surface clean
- **RaceMessage dedupe key is `(text, category, starting_no, session)`** — captures the unique identity of a race-control message; the server can replay identical frames during high-frequency updates (PITFALLS.md #3)
- **state.cars returns `dict(self._cars)` (defensive copy)** so consumers cannot mutate internal state via the property; same for `stats_best_sectors`. `messages` and `qualifying` are already immutable tuples so no copy needed
- **freshness defaults to RESYNCING**, not FRESH — a fresh `RaceState()` is honest about being empty until the first `apply()`. The plan's smoke test asserts this explicitly
- **Source defaults to LIVE** — the natural default for a new connection; REPLAY is set by the recorder/replay wrapper, IMPORTED by the JSON loader (both 02-03 / Phase 3 work)
- **No locks, no asyncio** — `apply()` is sync. The single-writer contract means the consumer's asyncio task is the only writer; the read-side properties are also sync so they can be called from any context (HTTP handler, dashboard, CLI). Locking would add overhead for no correctness benefit under the single-writer contract
- **Removed unused `TimeSyncMessage` / `UnknownMessage` imports from race_state.py** because they are no-op'd in `apply()` (forward-compat / heartbeat) and ruff F401 flagged them. The `isinstance` dispatch in `apply()` deliberately omits them, so importing them at module level was dead code. The forward-compat contract is documented in the `apply()` docstring

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Lint] Removed dead `TimeSyncMessage` / `UnknownMessage` imports from race_state.py**
- **Found during:** Task 1 (ruff check after GREEN)
- **Issue:** Plan's reference code imports all 8 message types into race_state.py, but `TimeSyncMessage` and `UnknownMessage` are no-op'd (not dispatched) so the imports are dead. ruff F401 flagged them
- **Fix:** Removed the two imports. The forward-compat contract is preserved (documented in `apply()` docstring and verified by the `test_apply_time_sync_is_noop` / `test_apply_unknown_is_noop` tests)
- **Files modified:** `src/aionlslivetiming/state/race_state.py`
- **Verification:** `ruff check` clean, all 120 tests still pass
- **Committed in:** `a64b7fd`

**2. [Rule 1 - Lint] Removed unused `TimeOfDay` import from test_state_freshness.py**
- **Found during:** Task 1 (ruff check after GREEN)
- **Issue:** Test file imported `TimeOfDay` but the freshness tests don't use it (they cover source/clear/last_update_ms, not track-state flattening)
- **Fix:** Removed the unused import
- **Files modified:** `tests/test_state_freshness.py`
- **Verification:** `ruff check` clean
- **Committed in:** `a64b7fd`

**3. [Rule 1 - Lint] Wrapped E501 long-line in test_state_apply.py:351**
- **Found during:** Task 1 (ruff check after GREEN)
- **Issue:** Plan's `state_to_dict()` helper had a 106-char line for the `stats_leading` list comprehension
- **Fix:** Wrapped the line at the `[` and indented the comprehension body
- **Files modified:** `tests/test_state_apply.py`
- **Verification:** `ruff check` clean
- **Committed in:** `a64b7fd`

---

**Total deviations:** 3 auto-fixed (all Rule 1 lint cleanups)
**Impact on plan:** All three were cosmetic / dead-code cleanups. No behavior change. Plan's correctness contract (27 tests, idempotency, freshness, pydantic models) implemented as specified.

## Issues Encountered

None. The plan's reference code translated directly to the implementation; only the three lint cleanups (above) were needed. Coverage, mypy, and the full test suite passed on the first GREEN run.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Ready for Plan 02-02 (filters)**: All read-side properties (`state.cars`, `state.standings()`, `state.laps(starting_no, session=...)`, `state.messages`, `state.qualifying`, `state.stats_leading`, `state.stats_best_laps`, `state.stats_best_sectors`) are in place for the filter DSL to build on.

**Ready for Plan 02-03 (persistence)**: `state_to_dict()` is a starting point; the JSON serializer will use `CarState.model_dump()` / `TrackState.model_dump()` and the same key shapes (tuple keys on `_laps` and `_stats_best_sectors` will serialize to string keys for JSON).

**Open design question (unchanged from Phase 1 STATE)**: The filter API shape — method-on-cache (`state.standings().filter(class_name="SP9")`) vs. builder-pattern query object (`Query(state).by_class("SP9").execute()`) — is still open and is the topic of Plan 02-02. Phase 1 STATE already flagged it for `/gsd-discuss-phase` resolution.

**Open research spikes (unchanged)**: Azure App Service idle timeout, `websockets` ping tuning, and `LTS_NOT_FOUND` three-state policy still need a `/gsd-research-phase` spike before Phase 3. Capture a real JSONL during a live test session before declaring Phase 3 done.

## Self-Check: PASSED

- All 9 source files exist (6 in `src/aionlslivetiming/state/` + 3 in `tests/test_state_*.py`)
- Both commits exist: `de19b3e` (RED: failing tests) and `a64b7fd` (GREEN: implementation)
- `uv run pytest` reports **120 passed** at **94.33% coverage** (80% gate met)
- `uv run mypy --strict src/aionlslivetiming/` reports **Success: no issues found in 32 source files**
- `uv run ruff check src/aionlslivetiming/state/ tests/test_state_*.py` reports **All checks passed!**
- Manual smoke test from plan verification block passes: `from aionlslivetiming import RaceState, Source, Freshness; ... assert s.cars == {}` after `clear()`

---
*Phase: 02-state-filtering*
*Completed: 2026-06-20*
