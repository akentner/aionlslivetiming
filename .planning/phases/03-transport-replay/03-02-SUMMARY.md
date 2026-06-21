---
phase: 03-transport-replay
plan: 02
subsystem: transport
tags: [async, websocket, websockets, multiplexer, keepalive, classifier, exponential-backoff, jitter, jsonl, protocol]

# Dependency graph
requires:
  - phase: 03-transport-replay (plan 01)
    provides: Transport Protocol (runtime_checkable), ClockOffset, ReconnectPolicy, LTSNotFoundEvent/Reason, exception hierarchy, ReplayTransport, JsonlRecorder
  - phase: 01-foundation-package-parser
    provides: Message dataclasses (InitialStateMessage, TrackStateMessage, TimeSyncMessage), parser.parse() dispatcher, jsonl_logger D-07 websockets_factory injection pattern
provides:
  - LiveTransport — the WebSocket-based live implementation of Transport (D-01..D-13)
  - LTSNotFoundPolicy — per-reason override for the LTS_NOT_FOUND three-state classifier (D-07, D-08)
  - _ConnectionState — internal per-session bookkeeping (last-frame-time watchdog, ended_seen flag)
  - _Sentinel / _SentinelKind — distinguish natural close from reconnect exhaustion (EXHAUSTED sentinel)
affects:
  - phase: 03-transport-replay (plan 03 — RecordingTransport wrapper, HTTP fallback)
  - phase: 04-client-distribution (NLSClient composition root uses LiveTransport)

# Tech tracking
tech-stack:
  added:
    - "websockets>=15.0.1,<17 — multiplexed WebSocket client with explicit handshake (no auto-ping; we drive keepalive)"
    - "orjson — optional JSON speedup, stdlib fallback (D-10 invariant)"
  patterns:
    - "Three independent async iterators fed by three asyncio.Queue instances (D-04 separation of message/time_sync/lts_not_found streams)"
    - "app-level keepalive: websockets ping_interval=None, ping_timeout=None; LiveTransport watches last_frame_at_s and cancels reader on idle (D-02)"
    - "full-jitter exponential backoff: random.uniform(0, min(cap, base * 2**attempt)) per AWS Architecture Blog (D-10)"
    - "EXHAUSTED sentinel vs END sentinel: distinguishes natural end-of-stream from reconnect exhaustion and from D-07 'ended' termination"
    - "pending-exception handoff: UnknownEventError raised inside reader is stored on transport and re-raised by the iterator on EXHAUSTED (the broad 'except Exception' in _reader_loop would otherwise swallow it)"
    - "websockets_factory injection pattern (mirrors jsonl_logger D-07) — every test injects a scripted-frame mock; no network in CI"
    - "PID-0 'shortcode' fallback in parser: when a payload sets PID==0 but no eventPid, the dispatcher falls back to PID for routing (already established; relevant because LTS_NOT_FOUND can arrive this way)"

key-files:
  created:
    - src/aionlslivetiming/transport/_connection.py — _ConnectionState dataclass (last_frame_at_s watchdog, ended_seen, first_lts_not_found_at_ms)
    - src/aionlslivetiming/transport/websocket.py — LiveTransport + LTSNotFoundPolicy + _Sentinel machinery
    - tests/test_live_transport.py — handshake, frame dispatch, close codes, idle watchdog, max_attempts
    - tests/test_live_reconnect.py — backoff formula, ReconnectPolicy defaults, frozen dataclass
    - tests/test_lts_not_found.py — 3-state classification, per-reason defaults, policy overrides
  modified:
    - src/aionlslivetiming/transport/__init__.py — re-export LiveTransport + LTSNotFoundPolicy
    - src/aionlslivetiming/__init__.py — top-level re-export LiveTransport + LTSNotFoundPolicy

key-decisions:
  - "LTS_NOT_FOUND classifier: 'not_yet_started' = connection age < pre_race_threshold_s AND no initial state with results; 'ended' = a TrackStateMessage had FINISHED/CHEQUERED or non-empty ENDTIME; 'unknown_event' = fallback. This ordering matters — ended_seen is checked first."
  - "Default policy (D-07): not_yet_started → continue (silent reconnect); ended → terminate (stop reconnecting, mark transport.ended=True); unknown_event → raise UnknownEventError."
  - "max_attempts exhaustion surfaces as EXHAUSTED sentinel on the messages queue — distinct from END sentinel (close()). The iterator sees EXHAUSTED and terminates; consumer code can distinguish by checking transport.ended vs inspecting for the sentinel."
  - "reader_task is the single owner of the WebSocket lifecycle. The watchdog task and the consumer's iterators all live in separate tasks; cancellation is the only synchronisation primitive."
  - "ping_interval=None + ping_timeout=None on the websockets connection (D-01). We drive keepalive from server {type:'time'} frames; the library would otherwise send pings the server may ignore."
  - "UnknownEventError is re-raised from the messages() iterator via a 'pending exception' attribute on the transport — the outer reader_loop's broad 'except Exception' cannot be widened without breaking the backoff cycle."
  - "LTSNotFoundPolicy is a non-frozen class (not a dataclass) because the three fields are validated in __init__ against an enum-like value set; frozen dataclasses can't enforce this elegantly without __post_init__."
  - "Test fixtures use both 'eventPid' (multiplex channel) and 'PID' (short-code payload key) — the parser dispatches on eventPid but the PID field is what real server payloads populate for the inner type."

patterns-established:
  - "Pattern: _Sentinel(_SentinelKind.EXHAUSTED) vs _SENTINEL_END — queue-level signal that survives task boundaries"
  - "Pattern: 'pending exception' attribute on the transport object — set by background task, raised by the public iterator on sentinel"
  - "Pattern: websockets_factory keyword arg + async-context-manager return — the canonical test injection shape, reusable for future HTTP-fallback tests"
  - "Pattern: full-jitter backoff documented with the exact formula min(cap, base * 2**attempt) — easier to reason about than decorrelated jitter, matches the AWS reference"
  - "Pattern: classifier side-effects on _ConnectionState (not on the transport) — keeps the transport class small and lets the state be unit-tested independently"

requirements-completed: [CONN-01, CONN-03, CONN-04, CONN-05, CONN-06, CONN-07, CONN-08]

# Metrics
duration: 9min
completed: 2026-06-21
---
# Phase 3 Plan 2: LiveTransport Summary

**WebSocket-based live Transport with multiplexed handshake, app-level keepalive from `{type:"time"}` frames, jittered exponential reconnect on transient close codes, and a stateful LTS_NOT_FOUND three-state classifier with per-reason policy**

## Performance

- **Duration:** 9 min 29 s
- **Started:** 2026-06-21T00:08:46Z
- **Completed:** 2026-06-21T00:18:15Z
- **Tasks:** 2
- **Files modified:** 7 (5 created, 2 modified)

## Accomplishments

- **LiveTransport is a real Transport implementer**: `isinstance(LiveTransport("evt-1"), Transport)` returns True; `__aiter__` yields typed `Message` instances (time-sync excluded per D-04); `transport.time_sync()` and `transport.lts_not_found()` expose the two dedicated streams (D-04, D-05).
- **LTS_NOT_FOUND three-state classifier (D-05..D-08)**: not_yet_started, ended, and unknown_event are correctly classified using the connection-age + ended_seen + initial_state heuristic. `LTSNotFoundPolicy` overrides per-reason defaults; invalid values raise at construction.
- **Jittered exponential backoff (D-09..D-13)**: full-jitter formula `random.uniform(0, min(cap, base * 2**attempt))`; `initial_offset_s` per-process random delay before first attempt; attempt counter resets after 60s successful session; `max_attempts=None` for infinite retry, `max_attempts=0` for no retry.
- **App-level keepalive (D-01..D-02)**: `websockets.connect(..., ping_interval=None, ping_timeout=None, close_timeout=5)` — the library does not auto-ping; `_idle_watchdog` cancels the reader task if no frame arrives in `idle_timeout_s` (default 90s), forcing reconnect.
- **No network in CI**: every test injects a scripted-frame mock via the `websockets_factory` keyword (D-07 pattern reused from `jsonl_logger`). 28 new transport tests, 238 total tests, all green.
- **Coverage on transport layer ≥ 87%** (DIST-06 gate): `_connection.py` 89%, `websocket.py` 87%, `base.py` 89%, `recorder.py` 88%, `replay.py` 87%. Overall total is dragged down by `state/persistence.py` (uncovered, pre-existing scope of Plan 02-03).

## Task Commits

Each task was committed atomically (TDD: red → green):

1. **Task 1: Build LiveTransport with handshake + keepalive + idle watchdog + close-code classification + reconnect loop** - `177b547` (feat)
2. **Task 1 RED:** `1d1c790` (test) — failing tests for handshake, frame dispatch, idle watchdog
3. **Task 2: Build LTS_NOT_FOUND three-state classifier + per-reason policy + classifier tests** - `d9c69bf` (test+fix) — classifier tests + exception-propagation fix

## Files Created/Modified

- `src/aionlslivetiming/transport/_connection.py` — `_ConnectionState` dataclass with `record_frame`, `observe_track_state`, `observe_initial_state`, `idle_seconds`, `connection_age_seconds`
- `src/aionlslivetiming/transport/websocket.py` — `LiveTransport` (handshake, reader loop, idle watchdog, classifier), `LTSNotFoundPolicy`, `_Sentinel` machinery
- `src/aionlslivetiming/transport/__init__.py` — re-exports `LiveTransport` and `LTSNotFoundPolicy`
- `src/aionlslivetiming/__init__.py` — top-level re-export of `LiveTransport` and `LTSNotFoundPolicy`
- `tests/test_live_transport.py` — 6 tests (handshake shape, frame dispatch, time-sync routing, ping_interval=None, idle watchdog, max_attempts=0)
- `tests/test_live_reconnect.py` — 11 tests (backoff formula parametrized, defaults, frozen dataclass)
- `tests/test_lts_not_found.py` — 10 tests (3-state classification, per-reason defaults, policy overrides, event immutability)

## Decisions Made

- **Full-jitter formula over decorrelated jitter** — simpler to reason about, matches the AWS Architecture Blog reference cited in the CONTEXT. Easier to verify in tests.
- **EXHAUSTED sentinel vs END sentinel** — `_Sentinel(_SentinelKind.EXHAUSTED)` is enqueued by both `_reader_loop` (on max_attempts) and `_handle_lts_not_found` (on `on_ended="terminate"`); `_SENTINEL_END` is enqueued by `close()`. Consumers see the same termination signal but can introspect `transport.ended` or `_pending_messages_exc` to distinguish.
- **Pending-exception handoff** — `UnknownEventError` raised inside the reader task is stored on `self._pending_messages_exc` before the raise, and re-raised by the `messages()` iterator when it sees the EXHAUSTED sentinel. This keeps the backoff cycle's `except Exception` narrow enough that the classifier exception is not swallowed.
- **Both `eventPid` AND `PID` in test fixtures** — the parser dispatches on `eventPid` (multiplex channel) but real server payloads also include `PID` (short-code payload key) for the inner type. Including both makes fixtures honest.
- **`pre_race_threshold_s=300.0` default** (5 min) — long enough to cover "we connected before the race started" but short enough that any reasonable startup sequence has cleared.
- **`idle_timeout_s=90.0` default** — well under Azure App Service's ~4 min idle timeout (Pitfall #1) so we detect silent close before Azure does.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] UnknownEventError was being swallowed by the reader_loop's broad except handler**
- **Found during:** Task 2 (writing classifier tests)
- **Issue:** `_handle_lts_not_found` raised `UnknownEventError` directly. The exception propagated up through `_session_loop` into `_reader_loop`'s `except Exception as exc: _log.warning("...session ended: %s", exc)` block, where it was logged and the backoff cycle continued. The consumer never saw the exception.
- **Fix:** Store the exception on `self._pending_messages_exc` before raising. The reader_loop catches `UnknownEventError` specifically (separate from the broad `Exception`) and stops the loop without backoff. The `messages()` iterator re-raises the pending exception when it sees the EXHAUSTED sentinel.
- **Files modified:** `src/aionlslivetiming/transport/websocket.py`
- **Verification:** `test_lts_not_found_unknown_event_default_raises` and `test_lts_not_found_yields_typed_event_before_raise` pass.
- **Committed in:** `d9c69bf` (Task 2 commit)

**2. [Rule 1 - Bug] Mock-WS fixture used wrong field names for parser routing**
- **Found during:** Task 2 (running classifier tests)
- **Issue:** Test fixtures used `"PID": 4` to mark track-state frames, but the parser dispatches on `eventPid` (multiplex channel id), not `PID` (short-code payload key). Without `eventPid: 4` in the fixture, the parser returned `UnknownMessage(event_pid=-1)` and the classifier never saw a TrackStateMessage to trigger `ended_seen=True`.
- **Fix:** Added `eventPid` alongside `PID` in the LTS_NOT_FOUND test fixtures (mirrors real server payloads which carry both).
- **Files modified:** `tests/test_lts_not_found.py`
- **Verification:** `test_lts_not_found_ended_after_trackstate_finished` and `test_lts_not_found_policy_continue_on_ended` now pass.
- **Committed in:** `d9c69bf` (Task 2 commit)

**3. [Rule 1 - Bug] Track-state TOD/ENDTIME fixture shape didn't match parser expectation**
- **Found during:** Task 2 (debugging the classifier)
- **Issue:** Test fixtures used `"TOD": "12:00:00"` (a plain string) but `parse_pid_4` expects `{"value": <ms>}` sub-dicts (mapped to `TimeOfDay`). The parser silently set `tod=None` and the classifier still worked — but the fixture was dishonest about real server payloads.
- **Fix:** Use the expected nested-dict shape: `"TOD": {"value": 43200000}`.
- **Files modified:** `tests/test_lts_not_found.py`
- **Verification:** TrackStateMessage now flows through with a valid `tod` attribute.
- **Committed in:** `d9c69bf` (Task 2 commit)

**4. [Rule 1 - Bug] Mock-WS yielded dicts but `_loads()` expected JSON text**
- **Found during:** Task 1 (running first tests)
- **Issue:** The mock `_MockWebSocket` yielded Python dicts directly, but `LiveTransport._loads()` calls `orjson.loads`/`json.loads` on the value — which expects JSON text. The real `websockets` library yields JSON-as-text on iteration, so the test was unfaithful to the production path.
- **Fix:** `_MockWebSocket.__init__` now serialises any non-string/bytes frames to JSON via `orjson` (fallback to stdlib). Test code can still pass dicts as frames; the mock handles the encoding.
- **Files modified:** `tests/test_live_transport.py`
- **Verification:** All 6 LiveTransport tests pass.
- **Committed in:** `177b547` (Task 1 commit)

**5. [Rule 3 - Blocking] Resolved ruff/mypy issues from imports and unused-ignore**
- **Found during:** Task 1 and Task 2 (running lint + typecheck)
- **Issue:** (a) `from collections.abc import Mapping` placed at end-of-file with an E402 comment — moved to the top imports. (b) `orjson` `# type: ignore[import-not-found]` flagged as `unused-ignore` when orjson is installed — removed the comment, mypy is happy either way. (c) `isinstance(item, Message)` rejected by mypy because `Message` is a `typing.Union` — replaced with a docstring comment explaining the queue contract.
- **Fix:** Applied directly per ruff's `--fix --unsafe-fixes` suggestions; removed unused-ignore comments; added explanatory comment instead of `assert isinstance(item, Message)`.
- **Files modified:** `src/aionlslivetiming/transport/websocket.py`, `tests/test_live_transport.py`, `tests/test_live_reconnect.py`, `tests/test_lts_not_found.py`
- **Verification:** `ruff check` clean; `mypy --strict src/aionlslivetiming/transport/` clean.
- **Committed in:** `177b547` and `d9c69bf`

---

**Total deviations:** 5 auto-fixed (4 bugs, 1 blocking lint/typecheck issue)
**Impact on plan:** All auto-fixes are correctness or test-integrity concerns. No scope creep — the public surface, requirements (CONN-01, 03, 04, 05, 06, 07, 08), and architecture are exactly as specified.

## Issues Encountered

None beyond the deviations above. The plan's reference code worked almost as-written; the small bugs caught during TDD are the kind the red-green cycle exists to surface.

The only pre-existing mypy `unused-ignore` errors in `cli/jsonl_logger.py`, `transport/recorder.py`, and `transport/replay.py` (3 total) are NOT in scope for this plan — they existed before Plan 03-02 and are caused by orjson being installed in the dev environment (the `# type: ignore[import-not-found]` comments on `import orjson` are now technically unused). They will be cleaned up at Phase 4 / distribution.

## User Setup Required

None - no external service configuration required. No new third-party dependencies (`orjson` remains an optional extra per D-10; stdlib `json` is the default fallback). `websockets` was already a transitive dev dependency through `pytest-respx` and others; it's now a direct runtime dependency.

## Next Phase Readiness

**Plan 03 (RecordingTransport wrapper)** is unblocked:
- LiveTransport is a real `Transport` implementer that can be composed with `JsonlRecorder`
- `time_sync()` exposes the time-sync stream (RecordingTransport may want to write those too, or not)
- All CONN-* requirements from Plan 02 are satisfied

**Plan 03 (HTTP fallback)** is unblocked:
- `httpx.AsyncClient` will be the consumer — same `websockets_factory` injection pattern can be mirrored with `httpx_transport_factory`

**No blockers or concerns** for either subsequent plan.

---

*Phase: 03-transport-replay*
*Completed: 2026-06-21*

## Self-Check: PASSED

- 03-02-SUMMARY.md: present
- src/aionlslivetiming/transport/_connection.py: present
- src/aionlslivetiming/transport/websocket.py: present
- tests/test_live_transport.py: present
- tests/test_live_reconnect.py: present
- tests/test_lts_not_found.py: present
- Commit 1d1c790 (test RED): present
- Commit 177b547 (Task 1 feat): present
- Commit d9c69bf (Task 2 test+fix): present
- 238 tests passing (was 210 before Plan 03-02, +28 new)
- ruff check: clean
- mypy --strict src/aionlslivetiming/transport/: clean
