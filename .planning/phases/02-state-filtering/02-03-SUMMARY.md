---
phase: 02-state-filtering
plan: 03
subsystem: state
tags: [persistence, json, round-trip, schema-versioning, pydantic, dataclasses]

# Dependency graph
requires:
  - phase: 02-state-filtering
    plan: 01
    provides: "RaceState facade with private attrs (_cars/_track/_messages/_laps/_qualifying/_stats_*) + CarState/TrackState/LapRecord pydantic models + enums (Source, Freshness)"
  - phase: 02-state-filtering
    plan: 02
    provides: "Filter DSL — proves the round-trip path must keep the read API stable"
provides:
  - "JSON snapshot persistence — state.to_json() exports the full cache; RaceState.from_json() / state.import_json() reconstruct / replace"
  - "STATE-06 satisfied: round-trip exports source / freshness / last_update_ms / track_name / ver / export_id / session / track / cars / messages / laps / qualifying / stats_leading / stats_best_laps / stats_best_sectors"
  - "STATE-07 satisfied: 13 fields reconstructed; idempotency-key set rebuilt from messages on import (D-PERSIST-3)"
  - "Schema version tag (schema_version=1) embedded for forward-compat (D-PERSIST-2)"
  - "Malformed JSON / missing schema_version / wrong version / non-object at top level all raise ValueError with a helpful message (D-PERSIST-5)"
  - "Stdlib json only — no orjson dep (D-PERSIST-1); orjson remains optional extra for downstream WS hot path"
affects:
  - "Phase 03 (transport): Live / Replay wrappers can persist state snapshots; downstream tools can archive / replay from JSON"
  - "Phase 04 (client + distribution): Discord bot / HA sensor can serialize state for bug reports and dashboards"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure functions (to_json / from_json) plus thin convenience methods on RaceState (to_json / import_json / from_json classmethod) — matches FastF1 session.load() pattern"
    - "Schema versioning as integer tag at JSON top — bump-and-raise policy for forward-compat"
    - "Idempotency contract preserved across round-trip — _seen_message_keys rebuilt from _messages list on import"
    - "Private attribute access from persistence.py — the one place that bypasses RaceState's public read surface to set internal state; documented as deliberate"
    - "Local imports in RaceState.to_json / import_json / from_json — keep persistence.py out of the top-level module graph to avoid circular deps"
    - "Manual reconstruction of stdlib dataclasses (SessionInfo / RaceMessage / CarResult) — no from_dict helper, keeps the events layer pure"

key-files:
  created:
    - src/aionlslivetiming/state/persistence.py
    - tests/test_state_persistence.py
  modified:
    - src/aionlslivetiming/state/race_state.py
    - tests/test_state_persistence.py (lint cleanup)

key-decisions:
  - "Stdlib json over orjson (D-PERSIST-1) — user-initiated path, not WS hot path; orjson stays optional extra"
  - "Schema version tag (schema_version=1) embedded at JSON top (D-PERSIST-2) — future bumps raise with a helpful message"
  - "Rebuild _seen_message_keys from _messages on import (D-PERSIST-3) — re-applying a stored RaceMessage after round-trip does NOT duplicate"
  - "Both instance methods (state.to_json / state.import_json) AND classmethod (RaceState.from_json) exposed (D-PERSIST-4) — matches FastF1 session.load() pattern + Python dataclasses.asdict convention"
  - "Malformed JSON / missing schema_version / wrong version / non-object all raise ValueError (D-PERSIST-5) — never silently return an empty state, that would mask corruption"
  - "Empty state round-trips cleanly (D-PERSIST-6) — RaceState() with no apply() produces equivalent empty state after round-trip"
  - "Filter is NOT serialized — it's a query object, not state (per 02-02-PLAN.md context)"

patterns-established:
  - "Pattern 1: Pure-function persistence layer + thin convenience methods — the public API surfaces instance methods for ergonomics but the core logic is a pure function for testability and reuse"
  - "Pattern 2: Round-trip with structural equality — to_json followed by from_json yields state with the same observable shape, including the _seen_message_keys set so idempotency survives"
  - "Pattern 3: Schema versioning as top-level integer — bump-and-raise policy keeps forward-compat simple; migration logic deferred until version 2"
  - "Pattern 4: dataclasses.asdict for stdlib dataclasses, model_dump for pydantic — each value type uses its native serialization mechanism"
  - "Pattern 5: Lazy imports inside methods to break circular deps — persistence.py and RaceState reference each other; importing inside the method body avoids module-level cycles"

requirements-completed: [STATE-06, STATE-07]

# Metrics
duration: ~10min
completed: 2026-06-20
---

# Phase 02 Plan 03: State JSON Snapshot Persistence

**JSON snapshot round-trip for RaceState — `to_json()` exports the full cache (source / freshness / last_update_ms / track_name / ver / export_id / session / track / cars / messages / laps / qualifying / stats_leading/best_laps/best_sectors) with an embedded schema_version tag; `from_json()` / `import_json()` reconstruct / replace, preserving the idempotency contract across the round-trip.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-20T23:07:00Z
- **Completed:** 2026-06-20T23:17:00Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 3 (2 created, 1 modified)
- **Tests added:** 10 (all green)

## Accomplishments

- **`src/aionlslivetiming/state/persistence.py`** — pure functions `to_json(state) -> str` and `from_json(s: str) -> RaceState` with `SCHEMA_VERSION = 1` and a clear ValueError policy
- **RaceState convenience surface** — `to_json()` (instance), `import_json(s)` (instance, replaces in-place), `from_json(s)` (classmethod, returns new) — matches FastF1's `session.load()` ergonomics
- **13 fields round-trip cleanly** — full pipeline through InitialStateMessage + TrackStateMessage + RaceMessage + PerCarLapsMessage + QualifyingMessage + StatisticsMessage survives to_json -> from_json with structural equality
- **Idempotency contract preserved** — `_seen_message_keys` is rebuilt from the `_messages` list on import; re-applying an already-stored RaceMessage after a round-trip does NOT duplicate (D-PERSIST-3)
- **Schema version tag (D-PERSIST-2)** — `{"schema_version": 1, ...}` at the JSON top; future bumps raise with a helpful message
- **Error policy (D-PERSIST-5)** — malformed JSON, missing `schema_version`, wrong version, or non-object at the top level all raise `ValueError` with a clear message; never silently returns an empty state (that would mask corruption)
- **10 new tests** — full round-trip, empty state round-trip, idempotency keys, replace (not merge), malformed JSON, missing schema version, wrong version, non-object, JSON validity, filter works on freshly-imported state
- **170 tests total** (was 160 in Phase 02 Plan 02), coverage on `state/` at **98%** (80% gate met; persistence.py itself at 98% — only line 141, the empty-list branch of stats_best_sectors loop, uncovered)
- **mypy --strict + ruff clean** across the full src + tests
- **Manual smoke test passes** — the REPL snippet from the plan's verification block confirms round-trip preserves class_name, track_name, ver, export_id

## Task Commits

TDD execution with 2 atomic commits:

1. **RED: Failing tests** — `e6ea23b` (test)
   - 10 test cases in `tests/test_state_persistence.py`
   - All 10 confirmed failing with `AttributeError: 'RaceState' object has no attribute 'to_json'` etc.
2. **GREEN: Implementation** — `a9b90a0` (feat)
   - `src/aionlslivetiming/state/persistence.py` (144 lines)
   - `src/aionlslivetiming/state/race_state.py` extended with `to_json()` / `import_json(s)` instance methods and `from_json(s)` classmethod
   - All 170 tests green (160 previous + 10 new)
   - Lint cleanups: removed unused `# type: ignore[attr-defined]` directives (mypy reported them as unused-ignore since the class attributes are statically known), E501 line wrap on a comment line

## Files Created/Modified

### Created

- `src/aionlslivetiming/state/persistence.py` (144 lines) — `to_json` and `from_json` pure functions with `SCHEMA_VERSION = 1`. Private-attribute access from a non-method module is intentional and documented; this is the one place that constructs a RaceState by setting `_cars` / `_track` / etc. directly (the normal constructor doesn't accept these because they're meant to be populated through `apply()`)
- `tests/test_state_persistence.py` (220 lines) — 10 tests covering all the must-have truths + 4 negative-path ValueError tests

### Modified

- `src/aionlslivetiming/state/race_state.py` — added three convenience methods (`to_json` instance, `import_json` instance, `from_json` classmethod) plus three private helpers used by `import_json`. Lazy-imports `persistence` inside the methods to avoid a top-level circular dependency (persistence.py imports RaceState; RaceState's methods import persistence)

## Decisions Made

- **Stdlib json over orjson** — per D-PERSIST-1 the persistence path is user-initiated (export / import), not on the WS hot path. orjson stays an optional extra for downstream consumers who may want to speed up recording or the future transport hot path. Avoids the dep
- **Schema versioning as integer** — per D-PERSIST-2 `{"schema_version": 1}` sits at the JSON top. Future STATE-06 iterations bump this to 2 and `from_json` raises with a clear message. No migration logic in v1 — just the version tag. Bump-and-raise keeps forward-compat simple
- **Manual SessionInfo / RaceMessage / CarResult reconstruction** — these are stdlib frozen dataclasses without a `from_dict` helper. `dataclasses.asdict(...)` on the way out, `ClassName(**dict)` on the way in. Keeps the events layer pure (no I/O-shaped methods)
- **Lazy imports inside RaceState methods** — `persistence.py` imports `RaceState`, and `RaceState.to_json` / `import_json` import `persistence`. A top-level cycle would fail; lazy-importing inside the methods avoids it cleanly
- **import_json as instance method (not classmethod)** — it modifies `self`, so it must be an instance method. `from_json` is the classmethod for the "construct new" case; both shapes are exposed because both are ergonomic in different contexts
- **Empty state round-trips cleanly** — `RaceState()` with no `apply()` produces a JSON snapshot with `schema_version=1` and all other fields null/empty; `from_json(snap)` reconstructs an empty state. No surprises
- **`stats_best_sectors` survives the round-trip** — list-of-dicts shape `[{starting_no, sector, value_ms}]` ordered by key so the output is deterministic; re-imported as `dict[(int, int), int]` matching the internal storage

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Lint] Removed unused `# type: ignore[attr-defined]` directives (mypy `unused-ignore`)**
- **Found during:** Task 1 (GREEN, after first mypy run)
- **Issue:** Plan's reference code used `# type: ignore[attr-defined]` on every `state._foo = ...` line in persistence.py to suppress mypy strict's "private attribute access" warning. But mypy doesn't actually warn about private-attribute access in this case (the attributes are statically known via `__init__`); it flagged the comments themselves as unused-ignore (31 errors total: 17 in persistence.py, 14 in race_state.py)
- **Fix:** Removed all 31 `# type: ignore[attr-defined]` comments. The code compiles clean under `mypy --strict` without them
- **Files modified:** `src/aionlslivetiming/state/persistence.py`, `src/aionlslivetiming/state/race_state.py`
- **Verification:** `uv run mypy --strict src/aionlslivetiming/state/` reports `Success: no issues found in 8 source files`
- **Committed in:** `a9b90a0` (initial GREEN)

**2. [Rule 1 - Lint] Wrapped a long docstring comment line (E501)**
- **Found during:** Task 1 (GREEN, ruff check after auto-fix)
- **Issue:** A comment line `# Laps: list[{session, starting_no, lap: dict}] -> dict[(session, starting_no, lap_no), LapRecord]` exceeded 100 chars (E501)
- **Fix:** Split across two lines
- **Files modified:** `src/aionlslivetiming/state/persistence.py`
- **Verification:** `uv run ruff check` reports `All checks passed!`
- **Committed in:** `a9b90a0`

---

**Total deviations:** 2 auto-fixed (both lint cleanups)
**Impact on plan:** Both fixes were post-first-pass lint hygiene. The implementation matches the plan's reference code exactly in behaviour. No scope creep, no functional changes.

## Issues Encountered

None of substance. The plan's reference code translated directly to a working implementation; only the two auto-fixes above were needed. Coverage, mypy, ruff, and the full test suite passed on the first GREEN run after removing the unnecessary type-ignore directives.

## User Setup Required

None — no external service configuration required. This plan completes the persistence path for `RaceState` (the third and final public-API surface of Phase 02). Phase 03 will wire this into the transport wrappers; consumers (Discord bots, HA sensors, dashboards) can already use `state.to_json()` / `RaceState.from_json(s)` against any state populated by `state.apply(msg)`.

## Next Phase Readiness

**Phase 02 is complete.** All three plans (Plan 01 = reducer, Plan 02 = filter DSL, Plan 03 = persistence) shipped green. The public API surface `from aionlslivetiming import RaceState` now exposes:
- Write: `state.apply(msg)` — idempotent reducer
- Read: `state.cars`, `state.laps(no)`, `state.standings()`, `state.messages`, `state.qualifying`, `state.stats_*`, `state.track`, `state.track_name`, `state.session`, `state.ver`, `state.export_id`, `state.freshness`, `state.source`, `state.last_update_ms`
- Query: `state.filter().by_class(...).by_starting_no(...).by_driver(...).by_position(...).by_lap(...).sector_time_lt(...).top(...).cars()` + convenience pass-throughs
- Persist: `state.to_json()` / `state.import_json(s)` / `RaceState.from_json(s)`
- Lifecycle: `state.set_source(s)`, `state.clear()`

**Ready for Phase 03 (transport)**: Live / Replay wrappers can wrap the persistence layer for full snapshot-on-disconnect / restore-on-reconnect flows, and the recorder (JSONL logger, already shipped in Phase 01) can be paired with the snapshot logger for archive-and-replay scenarios.

**Open design questions (unchanged)**: The Phase 3 design questions (Azure App Service idle timeout, `websockets` ping tuning, `LTS_NOT_FOUND` three-state policy) still need a `/gsd-research-phase` spike before implementation. Capture a real JSONL during a live test session before declaring Phase 3 done.

## Self-Check: PASSED

- All 3 files exist (2 created + 1 modified)
- Both commits exist: `e6ea23b` (RED: failing tests) and `a9b90a0` (GREEN: implementation)
- `uv run pytest` reports **170 passed** at **95.15% coverage** (80% gate met)
- `uv run mypy --strict src/aionlslivetiming/` reports **Success: no issues found in 34 source files**
- `uv run ruff check src/aionlslivetiming/ tests/` reports **All checks passed!**
- Manual smoke test from plan verification block passes:
  ```python
  from aionlslivetiming import RaceState
  from aionlslivetiming.events import InitialStateMessage, SessionInfo, CarResult
  s = RaceState()
  s.apply(InitialStateMessage(pid=1, ver="1", export_id="x", track_name="Test",
                              session=SessionInfo(session="R1"),
                              results=(CarResult(starting_no=7, position=1, class_name="SP9"),)))
  snap = s.to_json()
  s2 = RaceState.from_json(snap)
  assert s2.cars[7].class_name == "SP9"
  assert s2.track_name == "Test"
  ```
  Both assertions pass; `print('Manual smoke test PASSED')` confirms.

---
*Phase: 02-state-filtering*
*Completed: 2026-06-20*