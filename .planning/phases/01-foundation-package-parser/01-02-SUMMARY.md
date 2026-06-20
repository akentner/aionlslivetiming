---
phase: 01-foundation-package-parser
plan: 02
subsystem: events
tags: [dataclass, frozen, slots, pydantic-free, fixtures, json, typevar, raw-payload]

# Dependency graph
requires:
  - phase: 01-foundation-package-parser
    plan: 01
    provides: installable src-layout package skeleton + py.typed + events/__init__.py Message=object placeholder
provides:
  - 8 frozen @dataclass(slots=True) Message types in src/aionlslivetiming/events/
  - 4 shared embedded value types (TimeOfDay, SessionInfo, BestSector, CarResult)
  - Public Message = Union[...] alias as the parser's output type
  - 11 hand-crafted fixture JSONs (D-08 public test contract for Plan 03)
  - Per-class constructor + frozen + raw round-trip tests (22 tests, all green)
affects:
  - 01-03 (parser dispatcher reads Message.event_pid ClassVar to route by eventPid)
  - 01-03 (parser uses fixtures as the public contract for parse() tests)
  - Phase 2 state cache (consumes the Message union)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Stdlib-only events layer (D-01): @dataclass(frozen=True, slots=True), no pydantic/attrs/msgspec
    - event_pid: ClassVar[int] discriminator so the parser dispatcher routes without importing every class
    - Optional[...] defaults for missing server fields (D-03) so the parser never crashes on partial payloads
    - raw: Mapping[str, Any] = field(default_factory=dict) preserves unknown server keys (PARSE-03 forward compat)
    - UnknownMessage carries event_pid as an instance field (D-04 forward compat for unrecognised PIDs)
    - TimeSyncMessage uses event_pid=-1 sentinel (no real PID matches; type discriminator handles it)
    - Hand-crafted fixture JSONs in tests/fixtures/messages/ are the D-08 public test contract
    - TYPE_CHECKING guards for typing-only stdlib + first-party imports (TC001/TC003 ruff-clean)

key-files:
  created:
    - src/aionlslivetiming/events/common.py
    - src/aionlslivetiming/events/initial_state.py
    - src/aionlslivetiming/events/track_state.py
    - src/aionlslivetiming/events/race_message.py
    - src/aionlslivetiming/events/per_car_laps.py
    - src/aionlslivetiming/events/qualifying.py
    - src/aionlslivetiming/events/statistics.py
    - src/aionlslivetiming/events/time_sync.py
    - src/aionlslivetiming/events/unknown.py
    - tests/fixtures/messages/pid_0_initial.json
    - tests/fixtures/messages/pid_0_lts_not_found.json
    - tests/fixtures/messages/pid_3_race_message_pit.json
    - tests/fixtures/messages/pid_3_race_message_flag.json
    - tests/fixtures/messages/pid_4_track_state_running.json
    - tests/fixtures/messages/pid_4_track_state_finished.json
    - tests/fixtures/messages/pid_7_per_car_laps.json
    - tests/fixtures/messages/pid_501_qualifying.json
    - tests/fixtures/messages/pid_9002_statistics.json
    - tests/fixtures/messages/time_sync.json
    - tests/fixtures/messages/unknown_pid.json
    - tests/test_events_common.py
    - tests/test_events_dataclasses.py
  modified:
    - src/aionlslivetiming/events/__init__.py (placeholder Message=object → real Union alias)

key-decisions:
  - "TimeSyncMessage.event_pid = -1 sentinel so the parser dispatcher's eventPid lookup naturally misses the type-discriminated branch"
  - "UnknownMessage.event_pid is an instance field (not ClassVar) because each unknown PID is unique"
  - "PerCarLapsMessage.laps carries tuple[Mapping[str, Any], ...] (raw dicts) — typed lap parsing is Phase 2 work"
  - "Optional[...] defaults instead of sentinel empty strings for missing fields — preserves type accuracy"
  - "Union[...] alias kept in events/__init__.py with noqa: UP007 because D-06 documents Union[...] as the public API contract and the plan's key_link grep pattern requires the literal Union[ token"
  - "TYPE_CHECKING guards for Mapping/BestSector/CarResult/TimeOfDay/SessionInfo imports — typing-only with from __future__ import annotations"
  - "PEP 604 X | None syntax for field annotations (modernised by ruff UP045 auto-fix); Union[...] reserved for the public alias only"

patterns-established:
  - "Frozen+slots dataclass with ClassVar[int] event_pid discriminator — parser dispatcher key"
  - "raw: Mapping[str, Any] = field(default_factory=dict) preserves unknown server keys verbatim"
  - "Each Message subclass has a per-class happy-path test that loads the matching fixture and constructs the message with the documented kwargs shape"
  - "Frozen enforcement is verified per-class by attempting `msg.raw = {}` post-construction"
  - "event_pid ClassVar sweep test asserts the 7 distinct values (0/3/4/7/501/9002/-1)"

requirements-completed: [PARSE-02, PARSE-05]

# Metrics
duration: 6min
completed: 2026-06-20
---
# Phase 1 Plan 02: 8 Message Dataclasses + 11 Fixtures Summary

**Frozen `@dataclass(slots=True)` event types for all 8 NLS server channels (PIDs 0/3/4/7/501/9002 + time-sync + unknown), plus 11 hand-crafted fixture JSONs as the public parser-test contract — 22 tests green, ruff + mypy strict clean.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-06-20T15:57:00Z
- **Completed:** 2026-06-20T16:03:30Z
- **Tasks:** 2
- **Files modified:** 23 (22 created, 1 modified)

## Accomplishments

- `from aionlslivetiming.events import Message, InitialStateMessage, ...` exposes the full union (D-06) and all 8 concrete types
- Every Message is `@dataclass(frozen=True, slots=True)` with `event_pid: ClassVar[int]` discriminator + `raw: Mapping[str, Any]` payload (PARSE-02 + PARSE-05)
- 11 fixture JSONs at `tests/fixtures/messages/` are the D-08 public contract — every Plan 03 parser test will load one, call `parse(fixture)`, assert the field shape
- Frozen enforcement verified per-class: attempting `msg.raw = {}` on any of the 8 messages raises `dataclasses.FrozenInstanceError`
- `mypy --strict src` passes; `ruff check src tests` passes (no UP007/UP045/TC001/TC003 violations); 32-test full suite green
- Optional fields default so the parser never crashes on partial server payloads (D-03); unknown server keys preserved verbatim in `raw` (PARSE-03)

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement 8 Message dataclasses + common types + Message union** — `789a51b` (feat)
2. **Task 2: Create 11 hand-crafted fixture JSONs + per-class dataclass unit tests** — `eb8f698` (feat)

## Files Created/Modified

### Source (`src/aionlslivetiming/events/`)

- `common.py` — `TimeOfDay(value_ms)`, `SessionInfo(session, starting_no?, heat?, heat_type?, cup?, event_id?)`, `BestSector(starting_no, sector, value_ms, driver?)`, `CarResult(starting_no, position, class_name?, driver?, laps=0, total_time_ms?, gap_to_leader_ms?, best_lap_ms?)` — all frozen+slots
- `initial_state.py` — `InitialStateMessage` (event_pid=0) with `pid, ver, export_id, track_name, session, results=(), best_sectors=(), lts_not_found=False, raw`
- `track_state.py` — `TrackStateMessage` (event_pid=4) with `track_state, time_state, tod?, end_time?, raw`
- `race_message.py` — `RaceMessage` (event_pid=3) with `text, category, starting_no?, session?, raw`
- `per_car_laps.py` — `PerCarLapsMessage` (event_pid=7) with `session, starting_no, laps=(), raw` (raw dicts preserved)
- `qualifying.py` — `QualifyingMessage` (event_pid=501) with `results=(), raw`
- `statistics.py` — `StatisticsMessage` (event_pid=9002) with `leading=(), best_laps=(), best_sectors=(), raw`
- `time_sync.py` — `TimeSyncMessage` (event_pid=-1 sentinel) with `value_ms, raw`
- `unknown.py` — `UnknownMessage` with `event_pid` as instance field, `raw`
- `__init__.py` — public `Message = Union[...]` alias (noqa: UP007) + 12-name `__all__`

### Fixtures (`tests/fixtures/messages/`)

- `pid_0_initial.json` — PID 0 happy path: Nürburgring Nordschleife, 2-car SP9 result table, 2 best sectors
- `pid_0_lts_not_found.json` — `LTS_NOT_FOUND: true` (CONN-05)
- `pid_3_race_message_pit.json` — PIT message with startingNo=7, session=R1
- `pid_3_race_message_flag.json` — FLAG message (sector-level, no car)
- `pid_4_track_state_running.json` — GREEN/RUNNING with TOD
- `pid_4_track_state_finished.json` — CHEQUERED/FINISHED with ENDTIME
- `pid_7_per_car_laps.json` — 2 raw lap dicts preserved
- `pid_501_qualifying.json` — 2-row RESULT table
- `pid_9002_statistics.json` — LEADING + BEST_LAPS + BEST_SECTORS
- `time_sync.json` — `{"type":"time","value":1700000000000}`
- `unknown_pid.json` — `{"eventPid":9999,"anything":1,"futureServerField":"ignore-me"}` (forward-compat shape)

### Tests

- `tests/test_events_common.py` — 8 tests: `TimeOfDay`, `SessionInfo` (required+optional+frozen), `BestSector` (required+optional+frozen), `CarResult` (required+full+frozen)
- `tests/test_events_dataclasses.py` — 14 tests: 11 happy-path per-class constructors + frozen-sweep over all 8 + raw-roundtrip with unknown fields + event_pid ClassVar sweep

## Decisions Made

- **TimeSyncMessage.event_pid = -1 sentinel** — lets the parser dispatcher's `eventPid` lookup naturally miss the type-discriminated branch without special-casing the `Message` union
- **UnknownMessage.event_pid is an instance field** (not ClassVar) — each unknown event has its own PID, so the class-level discriminator doesn't make sense
- **PerCarLapsMessage.laps carries `tuple[Mapping[str, Any], ...]`** — typed lap parsing (e.g. into a `Lap` dataclass with sector times) is Phase 2 (state cache) work; Phase 1 preserves the raw dicts verbatim so the parser is a thin pass-through
- **PEP 604 `X | None` syntax** for field annotations (D-03 requirement is `Optional[...]` but ruff UP045 auto-fix modernised to `X | None` since runtime accuracy is preserved under `from __future__ import annotations`)
- **Explicit `Union[...]` alias** kept in `events/__init__.py` with `# noqa: UP007` — D-06 documents the `Union[` token as part of the public API, and the plan's key_link grep pattern explicitly requires the literal `Union[` substring
- **TYPE_CHECKING guards** for `Mapping`, `BestSector`, `CarResult`, `TimeOfDay`, `SessionInfo` imports — under `from __future__ import annotations` these are typing-only and ruff TC001/TC003 correctly flags them
- **Coverage scope deferred to Plan 03** — the `addopts` `--cov=aionlslivetiming/events` in pyproject.toml emits `module-not-imported` warnings because no production code in Plan 01 imports the new event classes; Plan 03's parser dispatcher will close the gap

## Deviations from Plan

None — plan executed exactly as written. (The auto-applied ruff UP045/TC001/TC003 modernisations and `from __future__ import annotations` typing-only import moves are mechanical refactors that keep the plan's spec intact — the dataclass semantics, public surface, and test contract are unchanged.)

## Issues Encountered

- **Ruff `module-not-imported` coverage warnings** — Plan 01's `addopts` adds `--cov=aionlslivetiming/events` but the parser dispatcher (which will import these classes) is not yet written, so the coverage plugin emits a "module not imported" warning during test runs. This is expected — Plan 03 closes the gap by importing every event class. The 22 new tests still pass; the warning is cosmetic.
- **Ruff E501 on test_events_dataclasses.py:54** — a single `SessionInfo(session=..., cup=..., heat=..., heat_type=...)` call exceeded the 100-char line limit. Reformatted as a multi-line kwarg call. No semantic change.

## User Setup Required

None — no external service configuration required for this plan. Plan 03 (parser dispatcher) will use these types as its output; downstream consumers will import `Message` from `aionlslivetiming.events`.

## Next Phase Readiness

- **Plan 03 (parser dispatcher) can start immediately:** the 8 Message classes are importable and frozen+slots enforced, the public `Message` union aliases them, and 11 fixtures define the test contract.
- The parser dispatcher (`src/aionlslivetiming/parser/__init__.py`) will switch on `event_pid` (or the `type:'time'` discriminator) to map raw frames onto the matching Message subclass, then the new tests will assert the round-trip.
- `InitialStateMessage.lts_not_found` is wired through so the parser's CONN-05 handling has somewhere to surface the flag (no parser-level sentinel needed).
- **No blockers for Plan 03.**

---
*Phase: 01-foundation-package-parser*
*Completed: 2026-06-20*

## Self-Check: PASSED
