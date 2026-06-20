---
phase: 01-foundation-package-parser
plan: 03
subsystem: parser
tags: [match-case, dispatcher, dataclass, frozen, slots, coverage-gate, pytest, warn-dedupe, lts-not-found]

# Dependency graph
requires:
  - phase: 01-foundation-package-parser
    plan: 02
    provides: 8 frozen @dataclass(slots=True) Message types + 11 hand-crafted fixture JSONs
provides:
  - 8 per-PID parser functions (parse_pid_0/3/4/7/501/9002) + parse_time_sync + parse_unknown
  - Shared parser/_helpers.py: warn_missing() with module-level (event_pid, field) dedupe set + safe type-cast builders
  - Public parse() dispatcher: match/case on eventPid, type-discriminated time-sync branch first, UnknownMessage fallback
  - Comprehensive unit test suite: dispatcher (12), per-PID specifics (8 files), logging contract (12)
  - 80% coverage gate on parser/+events/ enforced via pyproject.toml fail_under
  - Phase 1 close-out: package installable, 8 typed Messages, full parser dispatcher, ≥80% test coverage
affects:
  - Phase 2 (state cache) — consumes the parse() output (Message union) to maintain in-memory standings/lap/sector state
  - Phase 3 (transport) — wraps parse() in the live WebSocket client, the recording wrapper, and the JSONL replayer

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Pure-function parser layer — no I/O, no async, no transport (PARSE-04)
    - match/case over eventPid (Python 3.12+) for the public dispatcher — structural pattern matching keeps the dispatch table flat and exhaustive
    - Type-discriminated time-sync branch matches BEFORE the eventPid lookup (D-05) so the {type:'time'} frame never enters the race-message stream
    - UnknownMessage fallback for unrecognised eventPids (D-04 forward-compat) — every unknown PID emits exactly one WARNING per process
    - Module-level _warned: set[tuple[int, str]] in _helpers.py — shared dedupe set across all 8 per-PID parsers + dispatcher (D-03)
    - safe _opt_int / _opt_str / _time_of_day / _session_info / _car_result / _best_sector builders that never raise (D-03)
    - Autouse reset_warned() fixture in conftest.py so tests are order-independent
    - Failed-to-fail coverage addopts use dotted module names (--cov=aionlslivetiming.parser) so the coverage tool can actually discover the packages

key-files:
  created:
    - src/aionlslivetiming/parser/_helpers.py
    - src/aionlslivetiming/parser/initial_state.py
    - src/aionlslivetiming/parser/track_state.py
    - src/aionlslivetiming/parser/race_message.py
    - src/aionlslivetiming/parser/per_car_laps.py
    - src/aionlslivetiming/parser/qualifying.py
    - src/aionlslivetiming/parser/statistics.py
    - src/aionlslivetiming/parser/time_sync.py
    - src/aionlslivetiming/parser/unknown.py
    - tests/test_parser_dispatcher.py
    - tests/test_parser_initial_state.py
    - tests/test_parser_track_state.py
    - tests/test_parser_race_message.py
    - tests/test_parser_per_car_laps.py
    - tests/test_parser_qualifying.py
    - tests/test_parser_statistics.py
    - tests/test_parser_time_sync.py
    - tests/test_parser_unknown.py
    - tests/test_parser_logging.py
  modified:
    - src/aionlslivetiming/parser/__init__.py (channel-constant re-exports → real parse() dispatcher)
    - tests/conftest.py (added autouse reset_warned() fixture)
    - tests/fixtures/messages/pid_0_initial.json (added eventPid: 0 discriminator)
    - tests/fixtures/messages/pid_0_lts_not_found.json (added eventPid: 0 discriminator)
    - pyproject.toml (dotted-module cov paths, fail_under=80 coverage gate)

key-decisions:
  - "match/case over eventPid in the dispatcher — structural pattern matching reads as an exhaustive dispatch table"
  - "Type-discriminated time-sync branch is matched FIRST in parse() — {type:'time'} must never be treated as a race-message stream frame (D-05)"
  - "Single module-level _warned: set[tuple[int, str]] in _helpers.py — every parser shares one dedupe set so a single hot feed can never log-storm the WARNING handler (D-03)"
  - "Dispatcher falls back to PID==0 detection (raw['PID'] == 0) when eventPid is missing — defensive against LTS_NOT_FOUND frames that the server may send with the inner PID field but not the outer eventPid envelope"
  - "Fixtures pid_0_initial.json and pid_0_lts_not_found.json gained an explicit eventPid: 0 — the plan's dispatcher tests require the discriminator, and consistent routing beats a fragile special-case in the parser"
  - "UnknownMessage.event_pid is an instance field (not a ClassVar) — each unknown event carries its own PID"
  - "Coverage addopts use dotted module names (aionlslivetiming.parser) rather than the old forward-slash form (aionlslivetiming/parser) — the coverage tool could not discover the packages with the slashed form, leading to a 0% false negative"
  - "autouse reset_warned() in conftest.py — D-03 contract requires test independence; without this the first test to trigger a WARNING would silence the rest of the run"
  - "PATHOLOGICAL_INPUTS parametrize covers empty dict, type='not-time' (no eventPid), string eventPid, float eventPid — proves parse() never raises on any of these shapes (D-03)"

patterns-established:
  - "Pure-function parser leaf: def parse_pid_N(raw: Mapping[str, Any]) -> <MessageClass> — no I/O, no async, no logging beyond the shared warn_missing() helper"
  - "Shared _helpers.py private module: _warned set, warn_missing(), and 6 safe-cast builders — every parser imports from here so the D-03 contract is centralised"
  - "Per-PID parser does NOT log WARNING for absent optional fields beyond the per-PID minimum — only structural fields (PID, TRACKSTATE, etc.) trigger warn_missing; the per-PID parsers default optional arrays to () and let the dispatcher worry about unknown eventPids"
  - "Dispatcher test loads a fixture JSON and asserts isinstance + a key field value — the D-08 public test contract"
  - "Logging contract test pins warn_missing() dedupe semantics: same (event_pid, field) pair → 1 log; distinct field on same pid → 2 logs; same field on distinct pid → 2 logs; reset_warned() → 2 logs"

requirements-completed: [PARSE-01, PARSE-03, PARSE-04, DIST-06]

# Metrics
duration: 7min
completed: 2026-06-20
---
# Phase 1 Plan 03: parse() Dispatcher + Per-PID Parsers + Coverage Gate Summary

**`parse()` dispatcher over 6 NLS PIDs with type-discriminated time-sync branch, UnknownMessage forward-compat fallback, and ≥80% coverage gate — 92 tests pass, parser/+events/ coverage is 92%.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-06-20T14:08:56Z
- **Completed:** 2026-06-20T14:15:35Z
- **Tasks:** 2
- **Files modified:** 24 (19 created, 5 modified)

## Accomplishments

- `from aionlslivetiming.parser import parse` exposes the single entry point used by every transport (Phase 3) and the state cache (Phase 2)
- `parse(raw: Mapping) -> Message` dispatches on `type=='time'` first (D-05), then `match/case` on `eventPid` for the 6 known channels, with a `parse_unknown()` fallback for everything else (D-04) — never raises on missing or malformed input (D-03)
- 8 per-PID parser functions: `parse_pid_0` (initial state with LTS_NOT_FOUND branch), `parse_pid_3` (race messages), `parse_pid_4` (track state with TOD/ENDTIME), `parse_pid_7` (per-car laps), `parse_pid_501` (qualifying), `parse_pid_9002` (statistics) — each preserves `raw` (PARSE-03) and never raises on missing fields (D-03)
- Shared `parser/_helpers.py` consolidates the dedupe set, `warn_missing()` and 6 safe-cast builders so the D-03 contract is centralised
- WARNING logs deduped per `(event_pid, field_name)` tuple (D-03) — verified by 12 logging tests
- **Coverage on `parser/` and `events/` is 92%** (gate: 80%) — DIST-06 met
- All 16 short-code payload keys (`PID`, `VER`, `EXPORTID`, `SESSION`, `CUP`, `HEAT`, `HEATTYPE`, `TRACKNAME`, `STQ`, `BEST`, `TOD`, `RESULT`, `TRACKSTATE`, `TIMESTATE`, `ENDTIME`, `LTS_NOT_FOUND`) decoded into typed fields, each verified by at least one parser test (PARSE-01)
- `mypy --strict src` clean; `ruff check src tests` clean; full test suite (92 tests) green

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement 8 per-PID parser functions + parse_time_sync + parse_unknown** — `755c07a` (feat)
2. **Task 2: Implement parse() dispatcher + per-PID unit tests + log-dedupe tests + coverage gate** — `d87b327` (feat)

## Files Created/Modified

### Source (`src/aionlslivetiming/parser/`)

- `_helpers.py` — module-level `_warned: set[tuple[int, str]]` (D-03), `warn_missing()`, `reset_warned()` (test-only), `_opt_int`, `_opt_str`, `_time_of_day`, `_session_info`, `_car_result`, `_best_sector`
- `initial_state.py` — `parse_pid_0` reading `PID`/`VER`/`EXPORTID`/`TRACKNAME`/`SESSION`/`CUP`/`HEAT`/`HEATTYPE`/`RESULT`/`BEST`/`LTS_NOT_FOUND`
- `track_state.py` — `parse_pid_4` reading `TRACKSTATE`/`TIMESTATE`/`TOD`/`ENDTIME`
- `race_message.py` — `parse_pid_3` reading `text`/`type`/`startingNo`/`session`
- `per_car_laps.py` — `parse_pid_7` reading `session`/`startingNo`/`laps` (raw dicts preserved)
- `qualifying.py` — `parse_pid_501` reading `RESULT` array
- `statistics.py` — `parse_pid_9002` reading `LEADING`/`BEST_LAPS`/`BEST_SECTORS`
- `time_sync.py` — `parse_time_sync` reading `value` (no PID branch — type-discriminated)
- `unknown.py` — `parse_unknown(raw, event_pid)` forward-compat wrapper
- `__init__.py` — public `parse()` dispatcher with match/case, time-sync branch first, UnknownMessage fallback

### Tests (`tests/`)

- `test_parser_dispatcher.py` — 12 tests: every known PID, time-sync, unknown, type-takes-precedence-over-eventPid
- `test_parser_initial_state.py` — 8 tests: LTS_NOT_FOUND branch, missing RESULT/BEST, session info, best sectors, full result table, unknown fields, empty dict
- `test_parser_track_state.py` — 5 tests: running, finished, minimal, unknown field, malformed TOD
- `test_parser_race_message.py` — 5 tests: pit, flag, minimal, string startingNo cast, non-numeric fallback
- `test_parser_per_car_laps.py` — 5 tests: two laps, no laps, session+starting_no required, fallback to 0, empty dict
- `test_parser_qualifying.py` — 3 tests: two results, no result, partial row
- `test_parser_statistics.py` — 3 tests: all three sub-tables, all absent, only leading
- `test_parser_time_sync.py` — 5 tests: value, dispatch priority, raw preserved, empty value, malformed value
- `test_parser_unknown.py` — 2 tests: UnknownMessage construction, parse_unknown does not log (dispatcher does)
- `test_parser_logging.py` — 12 tests: D-03 dedupe contract — same field/same pid → 1 log, distinct field/same pid → 2 logs, same field/distinct pid → 2 logs, reset_warned() → 2 logs, dispatcher never raises, dispatcher unknown-PID logs, dispatcher unknown-PID dedupe, parametrised pathological inputs

### Fixtures

- `tests/fixtures/messages/pid_0_initial.json` — added `"eventPid": 0` discriminator
- `tests/fixtures/messages/pid_0_lts_not_found.json` — added `"eventPid": 0` discriminator

### Configuration

- `pyproject.toml` — `addopts` uses dotted module names (`--cov=aionlslivetiming.parser`) for coverage tool discovery; `[tool.coverage.report]` adds `fail_under = 80` (DIST-06 gate)
- `tests/conftest.py` — added `autouse=True` fixture calling `reset_warned()` before each test (D-03 test independence)

## Decisions Made

- **match/case over eventPid** — Python 3.12's structural pattern matching reads as an exhaustive dispatch table. Falls through cleanly to the UnknownMessage catch-all (D-04, D-06).
- **Type-discriminated time-sync branch is matched FIRST** — `{type:"time"}` must never be treated as a race-message stream frame (D-05). The dispatcher explicitly checks `raw.get("type") == "time"` before any `eventPid` lookup; the parametrised test `test_dispatch_time_sync_does_not_enter_pid_branch` proves the priority.
- **Single module-level `_warned: set[tuple[int, str]]` in `_helpers.py`** — every parser shares one dedupe set so a single hot feed emitting the same gap repeatedly can never log-storm the WARNING handler (D-03).
- **Dispatcher falls back to `PID == 0` detection** when `eventPid` is missing — defensive against stripped-down LTS_NOT_FOUND frames that the server might send with the inner sequence-counter `PID` field but no outer `eventPid` envelope.
- **Fixtures `pid_0_initial.json` and `pid_0_lts_not_found.json` gained explicit `eventPid: 0`** — the dispatcher tests require the discriminator, and consistent routing beats a fragile special-case in the parser.
- **Coverage addopts use dotted module names** — the old forward-slash form (`aionlslivetiming/parser`) silently made the coverage tool emit 0% because it could not discover the packages as namespaces. Dotted form (`aionlslivetiming.parser`) is the correct syntax.
- **`autouse reset_warned()` fixture in `conftest.py`** — D-03 contract requires test independence. Without it, the first test to trigger a WARNING would silence the dedupe for the rest of the run and false-positive the dedupe test.
- **`test_parse_handles_pathological_inputs` parametrize** — covers empty dict, `type='not-time'` (no eventPid), string eventPid, float eventPid. Proves `parse()` never raises on any of these shapes (D-03).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed coverage reporting 0% because addopts used slashed module paths**
- **Found during:** Task 2 (running pytest --cov)
- **Issue:** `addopts` used `--cov=aionlslivetiming/parser --cov=aionlslivetiming/events` (forward slashes). The coverage tool did not recognise the slashed form as Python module names and emitted "module-not-imported" warnings, then 0% coverage. The 80% gate therefore failed spuriously — every test passed but coverage looked 0%.
- **Fix:** Changed the addopts to dotted module names (`--cov=aionlslivetiming.parser --cov=aionlslivetiming.events`). Coverage now reports 92% and the 80% gate passes.
- **Files modified:** `pyproject.toml`
- **Verification:** Full pytest run shows 92% coverage on `parser/+events/` with `Required test coverage of 80.0% reached. Total coverage: 91.90%`.
- **Committed in:** `d87b327` (Task 2 commit)

**2. [Rule 1 - Bug] Fixed dispatcher dropping PID 0 frames because the fixture lacked eventPid**
- **Found during:** Task 2 (manual dispatcher smoke test)
- **Issue:** `pid_0_initial.json` and `pid_0_lts_not_found.json` were crafted in Plan 02 to use the inner sequence-counter `PID` field (which can be 12345 for happy-path, 0 for the LTS_NOT_FOUND branch) and did not carry an `eventPid` envelope. The dispatcher's `raw.get("eventPid")` returned `None` for both, falling through to the UnknownMessage branch — directly contradicting the plan's "`test_dispatch_pid_0` … assert isinstance `InitialStateMessage`" and "`test_dispatch_pid_0_lts_not_found`" must-have tests.
- **Fix:** Updated both PID 0 fixtures to add `"eventPid": 0` as the discriminator. The `PID` field retains its role as the inner sequence counter; the `eventPid` is the channel selector. The dispatcher also gained a defensive `raw.get("PID") == 0` fallback in case a real server frame omits `eventPid` (e.g. a future LTS_NOT_FOUND shape).
- **Files modified:** `tests/fixtures/messages/pid_0_initial.json`, `tests/fixtures/messages/pid_0_lts_not_found.json`, `src/aionlslivetiming/parser/__init__.py`
- **Verification:** `test_dispatch_pid_0` and `test_dispatch_pid_0_lts_not_found` pass; manual smoke test of all 10 dispatch paths passes.
- **Committed in:** `d87b327` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes are correctness improvements in the test infrastructure. Fix #1 makes the coverage gate actually run (it was silently broken). Fix #2 makes the dispatcher honour the plan's test contract (PID 0 frames must route to InitialStateMessage). No scope creep.

## Issues Encountered

- **Initial `addopts` form silently produced 0% coverage** — the previous plan (01-01) used forward-slash paths for `--cov`, which the coverage tool cannot resolve to module names. The `coverage report --include=...` showed the file list with 0% even though the source was clearly being executed. Diagnosed by running `coverage run --source=aionlslivetiming.parser,aionlslivetiming.events -m pytest` and seeing "module-not-measured" warnings. Fixed by switching to dotted module names in `addopts`.
- **Editable install required for the coverage gate to work** — `uv pip install -e ".[dev]"` was needed so the package is registered in the importable namespace; running tests against the source tree alone produces the same 0% false negative. The conftest `sys.path.insert` trick is not enough on its own for coverage measurement.
- **TYPE_CHECKING imports count as uncovered lines** — `src/aionlslivetiming/events/initial_state.py` lines 23-25 (the `if TYPE_CHECKING:` block) appear in the coverage report as uncovered. This is harmless — TYPE_CHECKING blocks never execute at runtime — and the per-file 89% is well above the 80% gate. Could be silenced with a `[tool.coverage.report] exclude_lines` regex (`if TYPE_CHECKING:`) but is not necessary.
- **Ruff UP045 / RUF022 auto-fixes applied** — `Optional[X]` annotations in `_helpers.py` were modernised to `X | None` (UP045) and `__all__` was sorted (RUF022). Both are mechanical refactors that keep the plan's spec intact.

## User Setup Required

None — no external service configuration required for this plan. The `parse()` dispatcher is ready to be wired into Phase 2 (state cache) and Phase 3 (transport / live WebSocket / JSONL replayer).

## Next Phase Readiness

- **Phase 2 (state cache) can start immediately:** `parse(raw)` is the public entry point; the resulting `Message` union is the input to the state cache.
- **Phase 3 (transport) can start immediately:** the JSONL logger CLI (Plan 01) and the live WebSocket client (Plan 03) both feed raw `dict` frames into `parse()`. Replay reads JSONL line-by-line and calls `parse()` per line.
- **Phase 1 close — no blockers.** The package is installable, the 8 typed Messages are dispatchable, the dedupe contract is enforced, and the ≥80% coverage gate is met.
- **Open design question for Phase 2:** filter API shape — method-on-cache vs. builder-pattern query object. Flagged in STATE.md and resolved via `/gsd-discuss-phase` before Phase 2 planning.

---

*Phase: 01-foundation-package-parser*
*Completed: 2026-06-20*

## Self-Check: PASSED
