---
status: complete
phase: 01-foundation-package-parser
source: 01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md
started: 2026-06-20T17:50:00Z
updated: 2026-06-20T18:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Package install + import + version
expected: `import aionlslivetiming` works; `aionlslivetiming.__version__ == "0.1.0"`; 6 channel ID constants importable from `aionlslivetiming.parser` with values {0, 3, 4, 7, 501, 9002}.
result: issue
reported: "Wir haben kein pip, sondern uv. Es geht auch bestimmt mit uv, aber dann muss die Anweisung im Test überarbeitet werden"
severity: minor

### 2. py.typed PEP 561 marker
expected: `src/aionlslivetiming/py.typed` ships in the installed package. Verifiable by checking the file exists in the installed location and contains the PEP 561 marker.
result: issue
reported: "src/aionlslivetiming/py.typed ist vorhanden, aber leer"
severity: minor

### 3. JSONL logger CLI --help
expected: `python -m aionlslivetiming.cli.jsonl_logger --help` prints argparse usage describing the live-capture interface (event ID arg, output path arg, optional URL override).
result: pass

### 4. Test suite passes
expected: `pytest` runs the full test suite (92 tests) with all green. Coverage on `parser/` + `events/` reports ≥80% (gate met).
result: pass

### 5. Ruff + mypy strict clean
expected: `ruff check src tests` returns no errors. `mypy --strict src` returns no errors.
result: pass

### 6. Cold Start Smoke Test
expected: Kill any running test process. Clear `.coverage` and `__pycache__` directories. Run `uv pip install -e ".[dev]" --force-reinstall` (or equivalent fresh install). Run `pytest` from scratch — package boots, all tests execute, coverage gate passes. No import errors, no missing dependencies, no stale cache issues.
result: pass

### 7. 8 Message dataclasses importable from events
expected: `from aionlslivetiming.events import Message, InitialStateMessage, RaceMessage, TrackStateMessage, PerCarLapsMessage, QualifyingMessage, StatisticsMessage, TimeSyncMessage, UnknownMessage` all succeed. `Message` is a Union type alias. Each message has `event_pid` (ClassVar[int] for the 7 typed channels, instance field for UnknownMessage) and `raw` (Mapping).
result: pass

### 8. parse() dispatches PID 0 → InitialStateMessage
expected: Calling `parse({"eventPid": 0, "PID": 1, "VER": 2, "TRACKNAME": "Nürburgring", "SESSION": "R1", "RESULT": [], "BEST": []})` returns an `InitialStateMessage` instance with `track_name == "Nürburgring"` and `event_pid == 0`.
result: skipped
reason: "User noted: covered by existing unit tests (tests/test_parser_*.py)"

### 9. parse() handles LTS_NOT_FOUND
expected: Calling `parse({"eventPid": 0, "LTS_NOT_FOUND": true})` returns an `InitialStateMessage` with `lts_not_found == True` and no crash on missing structural fields.
result: skipped
reason: "User noted: covered by existing unit tests (tests/test_parser_*.py)"

### 10. parse() dispatches PID 3 → RaceMessage
expected: Calling `parse({"eventPid": 3, "text": "PIT", "type": "PIT", "startingNo": 7, "session": "R1"})` returns a `RaceMessage` with `text == "PIT"` and `starting_no == 7`.
result: skipped
reason: "User noted: covered by existing unit tests (tests/test_parser_*.py)"

### 11. parse() dispatches PID 4 → TrackStateMessage
expected: Calling `parse({"eventPid": 4, "TRACKSTATE": "GREEN", "TIMESTATE": "RUNNING", "TOD": 12345.0})` returns a `TrackStateMessage` with `track_state == "GREEN"` and a `TimeOfDay(value_ms=12345)` in `tod`.
result: skipped
reason: "User noted: covered by existing unit tests (tests/test_parser_*.py)"

### 12. parse() dispatches time-sync FIRST
expected: Calling `parse({"type": "time", "value": 1700000000000})` returns a `TimeSyncMessage` with `value_ms == 1700000000000`, NOT a RaceMessage — even though no `eventPid` is present.
result: skipped
reason: "User noted: covered by existing unit tests (tests/test_parser_*.py)"

### 13. parse() falls back to UnknownMessage
expected: Calling `parse({"eventPid": 9999, "anything": 1})` returns an `UnknownMessage` instance with `event_pid == 9999` and `raw == {"eventPid": 9999, "anything": 1}`. Emits exactly one WARNING log per process for that PID.
result: skipped
reason: "User noted: covered by existing unit tests (tests/test_parser_*.py)"

### 14. parse() never raises on missing fields
expected: Calling `parse({})` returns an `UnknownMessage` (no eventPid) without raising. Calling `parse({"type": "not-time"})` returns UnknownMessage. String or float eventPid is coerced or falls through gracefully.
result: skipped
reason: "User noted: covered by existing unit tests (tests/test_parser_*.py)"

### 15. Frozen enforcement on Messages
expected: Attempting `msg.raw = {}` on any constructed Message raises `dataclasses.FrozenInstanceError`. Verifiable by trying in Python REPL.
result: skipped
reason: "User noted: covered by existing unit tests (tests/test_events_dataclasses.py — frozen-sweep test)"

### 16. Raw payload preserved on Messages
expected: Parsing a frame with an unknown extra field (e.g. `{"eventPid": 0, "futureField": "x", ...}`) preserves `futureField` in the resulting message's `raw` mapping.
result: skipped
reason: "User noted: covered by existing unit tests (tests/test_parser_unknown.py + raw-roundtrip test)"

### 17. JSONL line format compatibility
expected: The JSONL logger writes lines shaped `{ts_recv_ms, raw}` (Phase 1) — a strict subset of Phase 2's planned `{ts_recv_ms, event_pid, raw, parsed}` schema. Verifiable by running the logger against a short fake stream and inspecting output lines.
result: pass

## Summary

total: 17
passed: 6
issues: 2
pending: 0
skipped: 9
blocked: 0

## Gaps

- truth: "Test instructions use `pip install -e \"[dev]\"`"
  status: failed
  reason: "User reported: Wir haben kein pip, sondern uv. Es geht auch bestimmt mit uv, aber dann muss die Anweisung im Test überarbeitet werden"
  severity: minor
  test: 1
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
- truth: "`src/aionlslivetiming/py.typed` contains the PEP 561 marker"
  status: failed
  reason: "User reported: src/aionlslivetiming/py.typed ist vorhanden, aber leer"
  severity: minor
  test: 2
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""