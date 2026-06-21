---
phase: 03-transport-replay
plan: 01
subsystem: transport
tags: [async, websocket, jsonl, pydantic-optional, protocol, exceptions]

# Dependency graph
requires:
  - phase: 01-foundation-package-parser
    provides: Message dataclasses (InitialStateMessage, TimeSyncMessage, etc.), parser.parse() dispatcher, jsonl_logger D-07 {ts_recv_ms, raw} line shape, get_logger() helper
  - phase: 02-state-filtering
    provides: RaceState apply() reducer that consumes parsed Messages
provides:
  - Transport Protocol (runtime_checkable) with connect/close/__aiter__
  - NLSError exception hierarchy (base + 7 subclasses — preliminary per D-EXC)
  - ReplayTransport (offline, async-iterator, speed_factor + D-07 backward-compat)
  - JsonlRecorder (async-isolated writer via asyncio.Queue, Pitfall #7)
  - ClockOffset (EWMA-smoothed server-time offset) + ReconnectPolicy (D-09 defaults)
  - LTSNotFoundEvent + LTSNotFoundReason Literal for Plan 02 LTS_NOT_FOUND handling
affects:
  - phase: 03-transport-replay (Plan 02 LiveTransport — needs Transport Protocol, exceptions, ClockOffset, ReconnectPolicy, LTSNotFoundEvent)
  - phase: 03-transport-replay (Plan 03 RecordingTransport — needs JsonlRecorder + ReplayTransport composition)
  - phase: 04-client-distribution (NLSClient composition root — uses exceptions, all transports)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "runtime_checkable Protocol for duck-typed Transport"
    - "asyncio.Queue + dedicated writer task for non-blocking, concurrent-safe I/O (Pitfall #7)"
    - "EWMA-smoothed clock offset (alpha=0.3) for jitter tolerance"
    - "D-10 invariant: every JSONL `raw` re-parsed through parser.parse(); `parsed` is informational only"
    - "Preliminary exception names; names may move at Phase 4 per D-EXC"
    - "ASYNC240-safe: file reads in async tests via asyncio.to_thread"
    - "errors loud on purpose: ReplayEmptyError / ReplaySchemaError / ReplayOrderingError for D-17 data-integrity"
    - "trailing bad JSON: log WARNING once + skip (looks-done-but-isnt pitfall)"

key-files:
  created:
    - src/aionlslivetiming/exceptions.py — NLSError + ConnectionError, UnknownEventError, ReplayError/ReplayEmptyError/ReplaySchemaError/ReplayOrderingError, NLSHttpFallbackUnavailable
    - src/aionlslivetiming/transport/__init__.py — public re-exports (Plan 02/03 placeholders)
    - src/aionlslivetiming/transport/base.py — Transport Protocol, ClockOffset, ReconnectPolicy, LTSNotFoundEvent/Reason
    - src/aionlslivetiming/transport/replay.py — ReplayTransport (reads JSONL, parses raw, honours speed_factor + suppress_time_sync)
    - src/aionlslivetiming/transport/recorder.py — JsonlRecorder (asyncio.Queue + isolated writer task)
    - tests/test_exceptions.py — 7 tests for the exception hierarchy
    - tests/test_transport_base.py — 7 tests for Protocol + ClockOffset + ReconnectPolicy + LTSNotFoundEvent
    - tests/test_replay_transport.py — 16 tests (error paths, speed_factor, suppress_time_sync, D-07 backward-compat, ClockOffset updates)
    - tests/test_jsonl_recorder.py — 10 tests (schema, round-trip, concurrent appends, idempotent close, context manager, parent dir creation, reopen-append)
  modified:
    - src/aionlslivetiming/__init__.py — re-export NLSError + subclasses, ClockOffset, ReconnectPolicy, LTSNotFoundEvent, ReplayTransport, JsonlRecorder, Transport

key-decisions:
  - "JsonlRecorder and ReplayTransport are populated in this plan (rather than left as Plan 02/03 placeholders) so the Transport isinstance check in test_transport_base.py can be backed by a real implementer — no Protocol without a witness"
  - "ReconnectPolicy defaults match D-09 (1.0/60.0/None/10.0/True) verbatim"
  - "ClockOffset uses EWMA alpha=0.3 (favors recent samples, smooths jitter)"
  - "ReplayTransport speed_factor: 0=burst (no sleeps), 1.0=real-time, >1=faster, <0=ValueError at construction"
  - "ReplayTransport applies the speed_factor sleep BEFORE yielding, not after — first message emits immediately"
  - "ReplayTransport captures prev_ts_for_sleep separately from the ordering-check prev_ts so the gap is computed between the previous line's ts and the current one (avoids the off-by-one ordering bug noted in the plan)"
  - "JsonlRecorder serialise_parsed() uses dataclasses.asdict() with getattr(msg, 'model_dump', None) fallback for pydantic state objects"
  - "JsonlRecorder writes to a single path across reopens (append mode) — supports the reopen-and-append use case"
  - "LTSNotFoundEvent is a frozen dataclass (not pydantic) per D-01 dataclass-on-events rule"
  - "Async test files use asyncio.to_thread() for pathlib I/O to satisfy ruff ASYNC240 without sacrificing test simplicity"
  - "ConnectionError shadows the builtin in our namespace — acceptable per the plan since `except NLSError` is the recommended catch pattern"

patterns-established:
  - "Pattern: Protocol satisfaction backed by a real implementer (never an abstract witness); isinstance(rt, Transport) just works"
  - "Pattern: dataclass(frozen=True) for events-layer values, dataclass (mutable) for internal helpers (ClockOffset)"
  - "Pattern: file I/O in async tests → asyncio.to_thread(sync_helper) to silence ASYNC240 without losing readability"
  - "Pattern: TDD as RED → GREEN + refactor (no separate refactor pass needed here; coverage is at 88-100% on transport/)"
  - "Pattern: docstring-per-class explains the *why* (locked decisions, refs to D-XX) — keeps Phase 4+ work aligned"

requirements-completed: [CONN-01, CONN-02, CONN-08, STREAM-01, STREAM-02, STREAM-03, STREAM-04, REC-01, REC-02, REC-03, REC-04, REC-05, REC-06]

# Metrics
duration: 5min
completed: 2026-06-21
---

# Phase 3 Plan 1: Transport Foundation Summary

**Transport Protocol (runtime_checkable), 8-class NLSError hierarchy, ReplayTransport with D-07 backward-compat + speed_factor, and async-isolated JsonlRecorder — all 12 transport-related requirements delivered with 210 passing tests**

## Performance

- **Duration:** 5 min
- **Started:** 2026-06-21T00:01:36Z
- **Completed:** 2026-06-21T00:06:41Z
- **Tasks:** 2
- **Files modified:** 9 created, 1 modified (`__init__.py`)

## Accomplishments

- **Transport Protocol is real**: `isinstance(ReplayTransport("/tmp/x"), Transport)` returns True; `__aiter__` yields typed Messages; `connect()`/`close()` are idempotent.
- **Exception hierarchy is complete and catchable**: `except NLSError` catches every concrete subclass (ConnectionError, UnknownEventError, ReplayError family, NLSHttpFallbackUnavailable). Preliminary names per D-EXC; documented as such.
- **Replay parity with live mode**: ReplayTransport reads JSONL, dispatches every `raw` payload through `parser.parse()` (D-10 invariant), honours `speed_factor` (0/1.0/>1/<0), and excludes time-sync by default while still updating ClockOffset (D-04/D-16).
- **D-07 backward-compat verified**: a Phase 1 JSONL with shape `{ts_recv_ms, raw}` (no `event_pid`, no `parsed`) replays correctly via the `raw.get("eventPid")` fallback.
- **Loud on bad data (D-17)**: empty file → ReplayEmptyError; missing `raw` → ReplaySchemaError(line_no); non-monotonic ts → ReplayOrderingError(line_no, prev, curr); invalid JSON trailing line → log WARNING once + skip.
- **Async-isolated writer (Pitfall #7)**: 20 concurrent appender coroutines produce 200 well-formed JSON lines, no interleaving — verified empirically.
- **Round-trip integrity**: `JsonlRecorder → ReplayTransport` yields the same typed Message (re-parsed from `raw`, per D-10).
- **Mypy --strict + ruff clean across all 39 source files; transport module coverage 88-100%, total 95%.**

## Task Commits

Each task was committed atomically:

1. **Task 1: Build exceptions + Transport Protocol + base helpers** - `84f8b2e` (feat)
2. **Task 2: Add comprehensive ReplayTransport + JsonlRecorder coverage** - `a252c07` (test)

## Files Created/Modified

- `src/aionlslivetiming/exceptions.py` — NLSError + 7 subclasses (preliminary per D-EXC)
- `src/aionlslivetiming/transport/__init__.py` — public re-exports
- `src/aionlslivetiming/transport/base.py` — Transport Protocol, ClockOffset, ReconnectPolicy, LTSNotFoundEvent
- `src/aionlslivetiming/transport/replay.py` — ReplayTransport (JSONL → parsed Messages, speed_factor + suppress_time_sync)
- `src/aionlslivetiming/transport/recorder.py` — JsonlRecorder (asyncio.Queue + isolated writer task)
- `src/aionlslivetiming/__init__.py` — top-level re-exports
- `tests/test_exceptions.py` — 7 tests
- `tests/test_transport_base.py` — 7 tests
- `tests/test_replay_transport.py` — 16 tests
- `tests/test_jsonl_recorder.py` — 10 tests

## Decisions Made

- Populated ReplayTransport + JsonlRecorder in this plan (not as Plan 02/03 placeholders) so the Transport isinstance check is backed by a real implementer; left `LiveTransport` and `RecordingTransport` as documented placeholders in `__all__` for Plans 02-03 to fill in.
- Speed_factor sleep is applied **before** yielding, not after — so the first message emits immediately and subsequent messages are paced by the gap to the previous line.
- Captured `prev_ts_for_sleep` separately from the ordering-check `prev_ts` so the speed_factor gap is computed between the previous line's ts and the current one (avoids the off-by-one noted in the plan).
- `JsonlRecorder._serialise_parsed()` uses `dataclasses.asdict()` for events-layer dataclasses, with a `getattr(msg, "model_dump", None)` fallback for any future pydantic state object that gets serialised through this path.
- Test helpers (`make_initial_msg`) now pass a complete `raw` dict including `eventPid` so the D-10 round-trip recovers the typed shape. This was a test fixture bug in the plan, not a library bug.
- Async test files use `asyncio.to_thread(_read_text, p)` to silence ruff ASYNC240 without sacrificing readability — alternative was `aiofiles`, but the file reads are tiny (test-sized) and the dependency is not justified.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `test_all_nls_errors_catchable_as_nls_error` test**
- **Found during:** Task 1 (writing the test)
- **Issue:** The plan's test called `raise cls("test")` for every concrete subclass, but `ReplayOrderingError(line_no, prev_ts, curr_ts)` requires 3 positional args — the test as written raised `TypeError` instead of verifying catchability.
- **Fix:** Restructured the test into a `cases: list[tuple[type, tuple]]` table so each class is constructed with the correct arguments. All 6 NLSError subclasses now correctly verify `except NLSError` catchability.
- **Files modified:** `tests/test_exceptions.py`
- **Verification:** All 7 exception tests pass.
- **Committed in:** `84f8b2e` (Task 1 commit)

**2. [Rule 1 - Bug] Fixed `make_initial_msg` test fixture in test_jsonl_recorder.py**
- **Found during:** Task 2 (running the round-trip test)
- **Issue:** The plan's helper built an `InitialStateMessage` with the default empty `raw={}` factory. After JsonlRecorder persisted `raw: {}`, ReplayTransport re-parsed `{}` and produced an `UnknownMessage(event_pid=-1)` instead of an `InitialStateMessage`, breaking the round-trip test.
- **Fix:** Updated `make_initial_msg()` to provide a complete `raw` dict (including `eventPid: 0`) matching what the parser would actually produce. This reflects how a real `Message` instance carries its original payload.
- **Files modified:** `tests/test_jsonl_recorder.py`
- **Verification:** `test_recorder_round_trips_with_replay` now passes; the round-trip contract is honestly tested.
- **Committed in:** `a252c07` (Task 2 commit)

**3. [Rule 1 - Bug] Fixed speed_factor `prev_ts` ordering bug from plan**
- **Found during:** Task 1 (implementing ReplayTransport.__aiter__)
- **Issue:** The plan's reference code updated `prev_ts = ts_recv_ms` before the speed_factor sleep, which would have made the next iteration compute the delta against the *new* line instead of the old one (a classic off-by-one).
- **Fix:** Captured `prev_ts_for_sleep` separately and only update it after the sleep is computed, so the gap is always between the previous line's ts and the current line's ts.
- **Files modified:** `src/aionlslivetiming/transport/replay.py`
- **Verification:** `test_replay_speed_factor_10_faster_than_real_time` passes (10x faster than real-time, not 11x or 9x).
- **Committed in:** `84f8b2e` (Task 1 commit)

**4. [Rule 3 - Blocking] Resolved ruff ASYNC240 in async test files**
- **Found during:** Task 2 (running `ruff check`)
- **Issue:** Async test functions used `pathlib.Path.read_text()` / `.exists()` directly, which triggered ruff ASYNC240 (pathlib ops block the event loop in async contexts).
- **Fix:** Wrapped test file reads in `asyncio.to_thread(_read_text, p)` using a tiny sync helper. Kept the test files readable while satisfying the lint rule. Did not introduce `aiofiles` since the reads are test-sized and the extra dependency is unjustified.
- **Files modified:** `tests/test_jsonl_recorder.py`, `tests/test_replay_transport.py`
- **Verification:** `ruff check` clean; all 26 transport tests pass; ASYNC240 not bypassed with noqa.
- **Committed in:** `a252c07` (Task 2 commit)

---

**Total deviations:** 4 auto-fixed (3 bugs, 1 blocking lint issue)
**Impact on plan:** All auto-fixes are correctness or test-integrity concerns. No scope creep — the public surface, requirements, and architecture are exactly as specified.

## Issues Encountered

None beyond the deviations above. The plan's reference code worked almost as-written, and the small bugs caught during TDD are the kind the red-green cycle exists to surface.

## User Setup Required

None - no external service configuration required. No new third-party dependencies (orjson remains an optional extra per D-10; stdlib `json` is the default fallback).

## Next Phase Readiness

**Plan 02 (LiveTransport)** is unblocked:
- Transport Protocol is published and runtime-checkable
- Exception hierarchy is in place
- ClockOffset + ReconnectPolicy are exposed at the top level
- LTSNotFoundEvent + LTSNotFoundReason are available for the three-state classification
- `transport/__init__.py` has `LiveTransport` listed in `__all__` and a comment for the Plan 02 import line

**Plan 03 (RecordingTransport wrapper)** is unblocked:
- JsonlRecorder is a real, tested, concurrent-safe implementer
- ReplayTransport can be iterated to feed the recorder
- The D-10 round-trip (write → read → equal Message) is verified

**No blockers or concerns** for either subsequent plan.

---
*Phase: 03-transport-replay*
*Completed: 2026-06-21*
