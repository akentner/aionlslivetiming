---
phase: 01-foundation-package-parser
verified: 2026-06-20T16:30:00Z
status: passed
score: 9/9 must-haves verified
---

# Phase 1: Foundation + Package + Parser Verification Report

**Phase Goal:** Foundation — installable, typed Python package with the parser layer (parse() dispatcher + 8 per-PID typed Message dataclasses + JSONL capture CLI + ≥80% coverage on parser/events).
**Verified:** 2026-06-20T16:30:00Z
**Status:** passed

## Goal Achievement

### Observable Truths

| #   | Truth                                                                | Status     | Evidence                                                         |
| --- | -------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------- |
| 1   | `pip install -e .` succeeds on Python 3.12 and `import aionlslivetiming` works with `__version__` set | ✓ VERIFIED | `.venv/bin/python -c "import aionlslivetiming; print(aionlslivetiming.__version__)"` → `version: 0.1.0` |
| 2   | `py.typed` PEP 561 marker shipped in the installed package           | ✓ VERIFIED | `(pathlib.Path(aionlslivetiming.__file__).parent / 'py.typed').exists()` → `True`; src marker is 0 bytes; `[tool.hatch.build.targets.wheel.force-include]` configured |
| 3   | `pytest` runs from project root and all suites pass                  | ✓ VERIFIED | `pytest --no-header -q` → `92 passed in 0.32s`                    |
| 4   | `python -m aionlslivetiming.cli.jsonl_logger --help` prints usage    | ✓ VERIFIED | CLI prints full argparse usage with positional `event_id`, `output` and `--host`/`--max-seconds` flags |
| 5   | pyproject.toml pins pydantic==2.13.4, websockets>=15.0.1,<17, httpx>=0.28,<0.29 | ✓ VERIFIED | `dependencies = ["pydantic==2.13.4", "websockets>=15.0.1,<17", "httpx>=0.28,<0.29"]` |
| 6   | Zero `homeassistant.*` imports in src/                                | ✓ VERIFIED | `grep -r homeassistant src/` → no matches                         |
| 7   | All 8 Message dataclasses are `@dataclass(frozen=True, slots=True)` with `event_pid` discriminator + `raw: Mapping[str, Any]` field | ✓ VERIFIED | Runtime check: 7 classes have `event_pid: ClassVar[int]` (0/3/4/7/501/9002/-1); UnknownMessage uses event_pid as instance field. All 8 have `frozen=True, slots=True`. All have `raw` field. |
| 8   | `parse(raw: dict) -> Message` dispatches on `eventPid`; time-sync branch runs before PID lookup; unknown PIDs return `UnknownMessage` with WARNING; never raises on missing/malformed input | ✓ VERIFIED | End-to-end test: all 11 fixtures route to correct Message type; `parse({'eventPid':9999})` → `UnknownMessage(event_pid=9999)`; `parse({})` for all 8 per-PID parsers constructs a valid Message with defaults (no raise) |
| 9   | Coverage on `aionlslivetiming/parser/` and `aionlslivetiming/events/` is ≥80% | ✓ VERIFIED | `Required test coverage of 80.0% reached. Total coverage: 91.90%` (gate enforced via `fail_under = 80` in `[tool.coverage.report]`) |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact                                                                          | Expected                                                | Status      | Details                                                       |
| --------------------------------------------------------------------------------- | ------------------------------------------------------- | ----------- | ------------------------------------------------------------- |
| `pyproject.toml`                                                                  | Hatchling + src-layout + HA-pinned deps + ruff/mypy/pytest/cov | ✓ VERIFIED  | name=`aionlslivetiming`, requires-python=`>=3.12`, deps correct, all dev tooling configured |
| `src/aionlslivetiming/py.typed`                                                   | PEP 561 marker                                          | ✓ VERIFIED  | 0-byte marker file, force-included in wheel                  |
| `src/aionlslivetiming/version.py`                                                 | `__version__ = "0.1.0"`                                 | ✓ VERIFIED  | Imports and prints `0.1.0`                                    |
| `src/aionlslivetiming/logging.py`                                                 | `get_logger(name)` helper                               | ✓ VERIFIED  | Thin wrapper over `logging.getLogger`; used by parser + cli  |
| `src/aionlslivetiming/__init__.py`                                                | Re-exports `__version__` + `get_logger`                 | ✓ VERIFIED  | Public surface                                                |
| `src/aionlslivetiming/parser/channels.py`                                         | Channel ID constants (0/3/4/7/501/9002)                | ✓ VERIFIED  | All 6 constants present and importable                        |
| `src/aionlslivetiming/parser/__init__.py`                                         | Public `parse(raw) -> Message` dispatcher               | ✓ VERIFIED  | Match/case on eventPid, time-sync branch first, UnknownMessage fallback, PID==0 fallback for LTS_NOT_FOUND |
| `src/aionlslivetiming/parser/_helpers.py`                                         | Shared dedupe set, `warn_missing`, safe-cast builders   | ✓ VERIFIED  | All helpers present; `_warned: set[tuple[int, str]]`, `reset_warned()` for tests |
| `src/aionlslivetiming/parser/{initial_state,track_state,race_message,per_car_laps,qualifying,statistics,time_sync,unknown}.py` | 8 per-PID `parse_pid_N` functions + `parse_time_sync` + `parse_unknown` | ✓ VERIFIED | All 8 parsers exist, accept empty dict, never raise (D-03) |
| `src/aionlslivetiming/events/{common,initial_state,track_state,race_message,per_car_laps,qualifying,statistics,time_sync,unknown,__init__}.py` | 8 frozen dataclass Messages + 4 shared types + Message union | ✓ VERIFIED | All 8 classes are `@dataclass(frozen=True, slots=True)` with event_pid + raw; `Message = Union[...]` re-exports them |
| `src/aionlslivetiming/cli/jsonl_logger.py`                                        | D-07 live-capture CLI                                   | ✓ VERIFIED  | `run()` async + `main()` argparse; websockets_factory injection for tests |
| `tests/conftest.py`                                                               | Pytest config + autouse `reset_warned()`                | ✓ VERIFIED  | `asyncio_mode="auto"`, autouse fixture present                 |
| `tests/fixtures/messages/*.json` (11 files)                                       | Public test contract for parser tests                   | ✓ VERIFIED  | All 11 fixtures load; each carries expected `eventPid` (or `type:'time'`) discriminator |
| `tests/test_smoke.py`                                                             | Sync smoke tests                                        | ✓ VERIFIED  | 4 tests: imports, version, channel IDs, no-homeassistant, py.typed |
| `tests/test_jsonl_logger.py`                                                      | Async JSONL logger tests                                | ✓ VERIFIED  | 6 tests, all green                                             |
| `tests/test_events_common.py` + `tests/test_events_dataclasses.py`                | Event dataclass + common types unit tests               | ✓ VERIFIED  | 22 tests, all green                                            |
| `tests/test_parser_*.py` (10 files)                                               | Dispatcher + per-PID + logging tests                    | ✓ VERIFIED  | 60+ tests, all green; covers pathological inputs parametrised  |

### Key Link Verification

| From                                       | To                                       | Via                                                   | Status     | Details                                                     |
| ------------------------------------------ | ---------------------------------------- | ----------------------------------------------------- | ---------- | ----------------------------------------------------------- |
| `pyproject.toml`                           | `src/aionlslivetiming/`                  | `packages = ["src/aionlslivetiming"]`                 | ✓ WIRED    | hatch wheel target                                         |
| `pyproject.toml`                           | `src/aionlslivetiming/py.typed`          | `force-include "src/aionlslivetiming/py.typed"`        | ✓ WIRED    | PEP 561 marker ships in installed wheel                    |
| `src/aionlslivetiming/parser/__init__.py`  | `src/aionlslivetiming/parser/*.py`       | `match/case` dispatch on `raw.get("eventPid")`        | ✓ WIRED    | All 6 PIDs + catch-all implemented                         |
| `src/aionlslivetiming/parser/__init__.py`  | `src/aionlslivetiming/parser/time_sync.py` | `if raw.get("type") == "time": return parse_time_sync(raw)` | ✓ WIRED    | Time-sync branch matched BEFORE PID lookup (D-05)          |
| `src/aionlslivetiming/parser/__init__.py`  | `src/aionlslivetiming/parser/unknown.py` | Catch-all falls through to `parse_unknown(raw, pid_int)` | ✓ WIRED    | UnknownMessage fallback (D-04)                              |
| `src/aionlslivetiming/parser/initial_state.py` | `src/aionlslivetiming/events/initial_state.py` | `InitialStateMessage(...)` constructor with typed fields | ✓ WIRED    | PARSE-03: raw preserved via `dict(raw)`                     |
| `src/aionlslivetiming/parser/_helpers.py`  | `src/aionlslivetiming/events/common.py`  | `CarResult(...)`, `BestSector(...)` constructions      | ✓ WIRED    | Shared embedded value types                                 |
| `tests/test_parser_*.py`                   | `tests/fixtures/messages/*.json`         | `json.loads(...)` and `parse(...)`                     | ✓ WIRED    | All parser tests load + assert against fixtures             |
| `pyproject.toml`                           | `[tool.coverage.report] fail_under = 80` | Coverage gate enforced at test time                    | ✓ WIRED    | Gate runs automatically with `pytest`; 91.90% ≥ 80%        |

### Data-Flow Trace (Level 4)

The parser layer is pure (PARSE-04) — there is no dynamic data flowing from a network/database; the only inputs are the 11 hand-crafted fixture JSONs and the parser's response is deterministic. Verified end-to-end:

| Input fixture                       | Parser output type            | Verified fields                                              |
| ----------------------------------- | ----------------------------- | ------------------------------------------------------------ |
| `pid_0_initial.json`                | `InitialStateMessage`         | track_name, session.session/cup/heat/heat_type, results[0], best_sectors[0], raw preserved (incl. STQ) |
| `pid_0_lts_not_found.json`          | `InitialStateMessage`         | lts_not_found=True                                           |
| `pid_3_race_message_pit.json`       | `RaceMessage`                 | text, category="PIT", starting_no, session                    |
| `pid_3_race_message_flag.json`      | `RaceMessage`                 | text, category="FLAG", sector preserved in raw                |
| `pid_4_track_state_running.json`    | `TrackStateMessage`           | track_state="GREEN", time_state="RUNNING", tod.value_ms       |
| `pid_4_track_state_finished.json`   | `TrackStateMessage`           | track_state="CHEQUERED", end_time.value_ms                   |
| `pid_7_per_car_laps.json`           | `PerCarLapsMessage`           | session, starting_no, laps tuple (2 raw dicts)                |
| `pid_501_qualifying.json`           | `QualifyingMessage`           | results tuple (2 entries)                                    |
| `pid_9002_statistics.json`          | `StatisticsMessage`           | leading, best_laps, best_sectors                             |
| `time_sync.json`                    | `TimeSyncMessage`             | value_ms=1700000000000, event_pid=-1 (sentinel)               |
| `unknown_pid.json`                  | `UnknownMessage`              | event_pid=9999, raw preserved                                |

All 16 short-code keys (PID, VER, EXPORTID, SESSION, CUP, HEAT, HEATTYPE, TRACKNAME, STQ, BEST, TOD, RESULT, TRACKSTATE, TIMESTATE, ENDTIME, LTS_NOT_FOUND) decode into typed fields, each verified by at least one parser test.

### Behavioral Spot-Checks

| Behavior                                                    | Command                                          | Result                          | Status  |
| ----------------------------------------------------------- | ------------------------------------------------ | ------------------------------- | ------- |
| Package imports with version                                | `.venv/bin/python -c "import aionlslivetiming; print(aionlslivetiming.__version__)"` | `version: 0.1.0`                | ✓ PASS  |
| py.typed ships in installed wheel                           | check `(Path(aionlslivetiming.__file__).parent / 'py.typed').exists()` | `True`                          | ✓ PASS  |
| CLI entry point reachable                                   | `.venv/bin/python -m aionlslivetiming.cli.jsonl_logger --help` | Prints full argparse usage       | ✓ PASS  |
| Zero homeassistant imports in src/                          | `grep -r homeassistant src/`                     | No matches                      | ✓ PASS  |
| All 8 dataclasses have frozen+slots+event_pid+raw           | Runtime introspection                           | All checks pass                  | ✓ PASS  |
| `parse()` never raises on empty input for any PID           | Runtime test on all 8 parsers                   | All construct valid Messages    | ✓ PASS  |
| Dispatcher routes all 11 fixtures correctly                | End-to-end test                                  | All route to expected type      | ✓ PASS  |
| Coverage ≥80% on parser/events                              | `pytest --no-header`                             | `Required test coverage of 80.0% reached. Total coverage: 91.90%` | ✓ PASS  |
| ruff check passes                                           | `.venv/bin/ruff check src tests`                 | `All checks passed!`            | ✓ PASS  |
| mypy strict passes                                          | `.venv/bin/mypy src`                             | `Success: no issues found in 26 source files` | ✓ PASS  |

### Requirements Coverage

| Requirement | Source Plan                | Description                                                                              | Status      | Evidence                                                                                  |
| ----------- | -------------------------- | ---------------------------------------------------------------------------------------- | ----------- | ----------------------------------------------------------------------------------------- |
| PARSE-01    | 01-03                      | Library decodes all known short-code JSON keys into typed Python objects                 | ✓ SATISFIED | All 16 short-code keys verified decoded in `parser/__init__.py` + 8 per-PID parsers       |
| PARSE-02    | 01-02                      | Library exposes 8 typed message classes                                                  | ✓ SATISFIED | All 8 frozen `@dataclass` classes in `src/aionlslivetiming/events/`; `Message = Union[...]` |
| PARSE-03    | 01-02, 01-03               | Unknown/new server fields preserved on `.raw`; never cause a crash                       | ✓ SATISFIED | Every per-PID parser does `raw=dict(raw)`; verified by `test_raw_preserves_unknown_fields` |
| PARSE-04    | 01-03                      | Parser is pure (no I/O, no event-loop dependency)                                        | ✓ SATISFIED | Grep-verified: no aiohttp/requests/urllib imports in parser; no `async def` in parser layer |
| PARSE-05    | 01-02                      | Each typed message is a frozen dataclass with explicit fields                            | ✓ SATISFIED | All 8 classes are `@dataclass(frozen=True, slots=True)` with explicit typed fields       |
| DIST-02     | 01-01                      | Library uses `py.typed` (PEP 561)                                                         | ✓ SATISFIED | `py.typed` marker file present + force-included in wheel + ships in installed package    |
| DIST-03     | 01-01                      | Library targets Python 3.12+ and documents it                                            | ✓ SATISFIED | `requires-python = ">=3.12"`; README quickstart mentions `pip install -e ".[dev]"`       |
| DIST-06     | 01-03                      | Library has ≥80% test coverage for parser/events                                         | ✓ SATISFIED | Coverage: 91.90% (gate 80%); `fail_under = 80` enforced in pyproject                     |
| DIST-07     | 01-01                      | Library uses HA-pinned dependency versions                                               | ✓ SATISFIED | `pydantic==2.13.4`, `websockets>=15.0.1,<17`, `httpx>=0.28,<0.29`                          |

All 9 requirement IDs declared in PLAN frontmatter are accounted for. **No orphaned requirements.**

### Anti-Patterns Found

| File                                | Line | Pattern              | Severity | Impact                                                                                  |
| ----------------------------------- | ---- | -------------------- | -------- | --------------------------------------------------------------------------------------- |
| `src/aionlslivetiming/parser/_helpers.py` | 71, 75, 84, 88 | `return None` (4×)   | ℹ️ Info  | Legitimate safe-cast fallbacks in `_opt_int`/`_opt_str` for malformed input (D-03 contract: never raise). Not a stub. |
| `src/aionlslivetiming/parser/__init__.py` | 73-74 | Defensive fallback `if pid is None and raw.get("PID") == 0: pid = 0` | ℹ️ Info | Documented defensive path for LTS_NOT_FOUND frames that omit `eventPid`; no risk of mis-routing normal frames. |

**No blocker anti-patterns.** No TODOs, FIXMEs, placeholders, console.log-only implementations, hardcoded empty returns in user-visible paths, or empty handlers.

### Human Verification Required

None — all claims in the phase goal are deterministically verifiable and have been verified:

- Phase goal's "installable package" → `import` succeeds with `__version__`
- "Typed Python package" → `py.typed` ships + mypy strict clean
- "parse() dispatcher" → dispatcher routes all 11 fixtures correctly
- "8 per-PID typed Message dataclasses" → all 8 importable, frozen+slots, with event_pid + raw
- "JSONL capture CLI" → `--help` reachable + tests pass
- "≥80% coverage on parser/events" → 91.90% reported with gate enforced

The D-07 JSONL live-capture CLI is ready to run against the real `wss://livetiming.azurewebsites.net/` endpoint as a user-facing acceptance step before Phase 2 work begins — this is end-to-end behaviour that needs a real network, so it is the only thing flagged for optional human verification.

---

## Summary

All 9 must-have truths verified. All 9 requirement IDs (PARSE-01..05, DIST-02, DIST-03, DIST-06, DIST-07) covered. Test suite: 92 tests passing. Coverage: 91.90% (gate 80%). Ruff + mypy strict clean. The two SUMMARY-documented auto-fixed bugs (slashed coverage paths → dotted, PID 0 fixtures missing `eventPid`) are both verified resolved.

**Phase goal achieved.** Ready for Phase 2 (state cache + filter API).

---

_Verified: 2026-06-20T16:30:00Z_
_Verifier: the agent (gsd-verifier)_