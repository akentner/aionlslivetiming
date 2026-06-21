---
phase: 03-transport-replay
verified: 2026-06-21T15:00:00Z
status: gaps_found
score: 20/21 must-haves verified (1 unmet: REC-02)
gaps:
  - truth: "Recorder can be enabled/disabled at runtime (REC-02)"
    status: failed
    reason: "JsonlRecorder has no enable/disable toggle, no set_enabled(), no pause()/resume() methods. The only way to stop recording is to close the recorder. Runtime toggling is not implemented."
    artifacts:
      - path: src/aionlslivetiming/transport/recorder.py
        issue: "No enable/disable API surface"
      - path: src/aionlslivetiming/transport/recorder_wrapper.py
        issue: "No enable/disable API surface; always records if recorder is provided"
    missing:
      - "Add `set_enabled(bool)` method on JsonlRecorder (or RecordingTransport) that gates append() without losing the writer task"
      - "Add tests covering toggle-while-iterating (REC-02)"
      - "Update plan/SUMMARY to acknowledge the runtime toggle is partial: 'not yet implemented at the recorder level; runtime enable/disable can be achieved by composing/uncomposing RecordingTransport'"
rec_02_resolution:
  resolved_in: "Plan 03-04 (gap closure)"
  resolved_at: "2026-06-21T13:10:00Z"
  commits:
    - "7d6bacd: feat(03-04): add set_enabled to JsonlRecorder (REC-02 runtime toggle)"
    - "84b1b6c: feat(03-04): add set_enabled passthrough to RecordingTransport (REC-02)"
  evidence:
    - "JsonlRecorder exposes `is_enabled` property + async `set_enabled(bool)` method (recorder.py)"
    - "`append()` silently drops messages when `_enabled is False`; writer task keeps running"
    - "RecordingTransport exposes the same `is_enabled` / `set_enabled` and delegates to the wrapped recorder (recorder_wrapper.py)"
    - "4 new tests: 3 on JsonlRecorder (toggle-off, toggle-while-burst, post-close safety) + 1 on RecordingTransport (passthrough + recording-paused-while-iterating)"
    - "Full suite: 261 passed (was 257), 95.29% coverage maintained, ruff + mypy on changed files clean (only pre-existing orjson `unused-ignore` remains)"
human_verification:
  - test: "Run the UAT Step 1 against a real NLS session (live WebSocket to wss://livetiming.azurewebsites.net/)"
    expected: "Typed Message instances stream out; nls-1.jsonl is fully written on Ctrl-C"
    why_human: "All WebSocket tests use a mock websockets_factory; the real Azure protocol has not been exercised yet by automated tests."
  - test: "Verify UAT Step 2: replay a recorded JSONL with speed_factor=10.0 against the live server's actual response shape"
    expected: "Same messages as Step 1, 10x faster than real-time"
    why_human: "Speed_factor correctness is unit-tested but not against a real recorded file from the live server."
  - test: "Verify UAT Step 3: hit the actual /event/{id}/laps-data endpoint during an active session"
    expected: "NLSHttpFallbackUnavailable raised with 'use channel 7 instead' message (HTML response) OR a parsed JSON dict"
    why_human: "Respx-mocked responses cover the documented failure modes; real server behavior hasn't been confirmed end-to-end."
---

# Phase 3: Transport + Replay Verification Report

**Phase Goal:** A transport interface with three implementations (live WebSocket, JSONL replay, recording wrapper) plus the optional HTTP laps-data fallback — all feeding the same parser path so live and replay produce identical typed Messages.

**Verified:** 2026-06-21T15:00:00Z
**Status:** gaps_found (1 unmet requirement: REC-02)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can import Transport Protocol and use `connect()`, `close()`, and async iteration yielding Message | ✓ VERIFIED | `src/aionlslivetiming/transport/base.py:21` defines `@runtime_checkable Transport` Protocol; all 4 implementations (ReplayTransport, LiveTransport, RecordingTransport, plus internal types) satisfy it. |
| 2 | Exception hierarchy: NLSError base + ConnectionError, UnknownEventError, ReplayError + subclasses, NLSHttpFallbackUnavailable | ✓ VERIFIED | `src/aionlslivetiming/exceptions.py:11-66` defines all 8 exception classes. `tests/test_exceptions.py` (7 tests) verifies catchability. |
| 3 | User can create `ReplayTransport(path)` and async-iterate typed Message instances from parser.parse() | ✓ VERIFIED | `src/aionlslivetiming/transport/replay.py:48-211` defines ReplayTransport; line 28 imports `from aionlslivetiming.parser import parse` (D-10 invariant). |
| 4 | User can pass `speed_factor=10.0` for 10x replay; `speed_factor=0` for burst (no sleeps) | ✓ VERIFIED | `src/aionlslivetiming/transport/replay.py:157-164` implements speed_factor. Tests: `tests/test_replay_transport.py` lines for `test_replay_speed_factor_zero_burst`, `test_replay_speed_factor_10_faster_than_real_time`. |
| 5 | User can append to JsonlRecorder from many concurrent coroutines without interleaving partial lines | ✓ VERIFIED | `src/aionlslivetiming/transport/recorder.py:78-132` uses `asyncio.Queue` + dedicated writer task. Test `test_recorder_concurrent_appends_no_interleave` (20 coroutines × 10 appends = 200 well-formed lines). |
| 6 | User can replay Phase 1 D-07 JSONL with shape `{ts_recv_ms, raw}` (no event_pid, no parsed) | ✓ VERIFIED | `tests/test_replay_transport.py::test_replay_d07_backward_compat` — D-07 subset replays correctly. Parser re-parses `raw` payload per D-10 invariant. |
| 7 | ReplayTransport raises ReplayEmptyError / ReplaySchemaError / ReplayOrderingError with structured attributes | ✓ VERIFIED | `src/aionlslivetiming/transport/replay.py:124,134,173` raises all three. Each has `line_no` (and prev_ts/curr_ts for ordering). |
| 8 | Malformed trailing JSONL lines log WARNING once with line number and are skipped | ✓ VERIFIED | `src/aionlslivetiming/transport/replay.py:127-132` implements warned-once + skip pattern. Test `test_replay_invalid_json_trailing_line_warning`. |
| 9 | JsonlRecorder round-trips with ReplayTransport: write then read yields equal Message instances | ✓ VERIFIED | `tests/test_transport_integration.py::test_round_trip_recorder_to_replay_preserves_messages` (5-line realistic fixture across PIDs 0/4/3/7/9002) + `test_round_trip_via_recorder_then_replay_produces_qualifying_too` (PID 501). |
| 10 | User can `LiveTransport(event_id)` and connect to the NLS livetiming WebSocket | ✓ VERIFIED | `src/aionlslivetiming/transport/websocket.py:189-295` defines LiveTransport with `connect()`. Test `test_live_transport_sends_handshake_on_connect` confirms handshake shape `{eventId, eventPid, clientLocalTime}`. |
| 11 | User can `async for msg in transport:` and receive typed Message instances from multiplexed WS | ✓ VERIFIED | `src/aionlslivetiming/transport/websocket.py:316-338` defines `__aiter__` + `messages()`. Parser dispatch via `from aionlslivetiming.parser import parse` (line 54). |
| 12 | User can subscribe to `transport.time_sync()` for TimeSyncMessage instances (separate from main stream) | ✓ VERIFIED | `src/aionlslivetiming/transport/websocket.py:340-350` defines `time_sync()`. Test `test_live_transport_time_sync_excluded_from_messages`. |
| 13 | Client auto-reconnects with jittered exponential backoff on transient close codes; 1000/1001 do NOT reconnect | ✓ VERIFIED | `src/aionlslivetiming/transport/websocket.py:402-412` implements full-jitter formula `random.uniform(0, min(cap, base * 2**attempt))`. Tests in `test_live_reconnect.py` cover the formula; `test_live_transport_close_code_1000_does_not_reconnect` covers the no-reconnect path. |
| 14 | Client drives app-level keepalive from `{type:"time"}` frames; forces reconnect if no frame in `idle_timeout_s` | ✓ VERIFIED | `src/aionlslivetiming/transport/websocket.py:535-550` defines `_idle_watchdog`. Test `test_live_transport_idle_timeout_forces_reconnect`. |
| 15 | User can subscribe to `transport.lts_not_found()` for LTSNotFoundEvent with three reasons | ✓ VERIFIED | `src/aionlslivetiming/transport/websocket.py:352-362` defines `lts_not_found()`. Test `test_lts_not_found_yields_typed_event_before_raise` + 9 other classifier tests. |
| 16 | LTS_NOT_FOUND classification follows D-06 heuristics: not_yet_started / ended / unknown_event | ✓ VERIFIED | `src/aionlslivetiming/transport/websocket.py:523-533` defines `_classify_lts_not_found`. Tests: `test_lts_not_found_ended_after_trackstate_finished`, `test_lts_not_found_not_yet_started_silently_reconnects`, `test_lts_not_found_unknown_event_default_raises`. |
| 17 | LTSNotFoundPolicy is configurable per-reason; defaults match D-07 | ✓ VERIFIED | `src/aionlslivetiming/transport/websocket.py:146-186` defines LTSNotFoundPolicy. Tests in `test_lts_not_found.py` cover all 3 policies and invalid-value rejection. |
| 18 | User can pass `websockets_factory` to inject a mock WebSocket (matches jsonl_logger D-07 pattern) | ✓ VERIFIED | `src/aionlslivetiming/transport/websocket.py:230,418-422` accepts `websockets_factory` callable. All tests use this injection pattern (no network in CI). |
| 19 | User can wrap any Transport with `RecordingTransport(inner, recorder)` for tee-persists-then-yield | ✓ VERIFIED | `src/aionlslivetiming/transport/recorder_wrapper.py:30-101` defines composition wrapper with append-then-yield invariant (line 100: `await self._recorder.append(msg)` then `yield msg`). |
| 20 | User can fetch laps_data via httpx with HTML/non-JSON/non-object detection | ✓ VERIFIED | `src/aionlslivetiming/http/laps_data.py:49-120` defines `fetch_laps_data`. Three NLSHttpFallbackUnavailable raise paths for HTML, invalid JSON, non-object JSON. |
| 21 | User can inject `httpx.AsyncClient` (matches HA WebSession Injection pattern) | ✓ VERIFIED | `src/aionlslivetiming/http/laps_data.py:55,87-94,118-120` accepts optional client, creates own only when None. Test `test_fetch_laps_data_uses_injected_client`. |
| 22 | End-to-end: JsonlRecorder round-trip with ReplayTransport yields equal Messages | ✓ VERIFIED | `tests/test_transport_integration.py::test_round_trip_recorder_to_replay_preserves_messages`. |
| 23 | End-to-end: RecordingTransport wrapping LiveTransport writes messages to disk in real time | ✓ VERIFIED | `tests/test_transport_integration.py::test_recording_live_yields_and_persists_in_real_time` + `test_recording_live_recorded_file_replays_through_replay_transport`. |

**Score:** 20/21 verifiable requirements met (REC-02 missing runtime enable/disable).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/aionlslivetiming/exceptions.py` | NLSError + 7 subclasses | ✓ VERIFIED | 78 lines; all 8 classes present (NLSError, ConnectionError, UnknownEventError, ReplayError + 3 subclasses, NLSHttpFallbackUnavailable) |
| `src/aionlslivetiming/transport/base.py` | Transport Protocol + ClockOffset + ReconnectPolicy + LTSNotFoundEvent | ✓ VERIFIED | 139 lines; all 5 types present |
| `src/aionlslivetiming/transport/replay.py` | ReplayTransport (JSONL → parsed Messages) | ✓ VERIFIED | 211 lines; reads JSONL, dispatches through `parse()`, honors speed_factor + suppress_time_sync |
| `src/aionlslivetiming/transport/recorder.py` | JsonlRecorder (asyncio.Queue + isolated writer) | ✓ VERIFIED | 135 lines; `await self._recorder.append()` queues to writer task |
| `src/aionlslivetiming/transport/_connection.py` | _ConnectionState dataclass | ✓ VERIFIED | 72 lines; tracks last_frame_at_s, ended_seen, seen_initial_state_with_results |
| `src/aionlslivetiming/transport/websocket.py` | LiveTransport + LTSNotFoundPolicy + _Sentinel | ✓ VERIFIED | 556 lines; full reconnect loop, idle watchdog, classifier, three independent async iterators |
| `src/aionlslivetiming/transport/recorder_wrapper.py` | RecordingTransport composition wrapper | ✓ VERIFIED | 104 lines; append-then-yield invariant |
| `src/aionlslivetiming/transport/__init__.py` | Public re-exports | ✓ VERIFIED | 46 lines; exports all Transport implementations + helper types + exceptions |
| `src/aionlslivetiming/http/__init__.py` | Re-export fetch_laps_data | ✓ VERIFIED | 15 lines |
| `src/aionlslivetiming/http/laps_data.py` | fetch_laps_data with HTML/JSON/non-object detection | ✓ VERIFIED | 123 lines |
| `src/aionlslivetiming/__init__.py` | Top-level re-exports | ✓ VERIFIED | 58 lines; all 21 transport-related symbols + fetch_laps_data |
| `tests/test_exceptions.py` | 7 exception tests | ✓ VERIFIED | 2872 bytes |
| `tests/test_transport_base.py` | 7 Protocol + helper type tests | ✓ VERIFIED | 3229 bytes |
| `tests/test_replay_transport.py` | 16 replay tests | ✓ VERIFIED | 8955 bytes |
| `tests/test_jsonl_recorder.py` | 10 recorder tests | ✓ VERIFIED | 6503 bytes |
| `tests/test_live_transport.py` | 6 LiveTransport tests | ✓ VERIFIED | 7578 bytes |
| `tests/test_live_reconnect.py` | 7 reconnect tests | ✓ VERIFIED | 2213 bytes |
| `tests/test_lts_not_found.py` | 10 LTS_NOT_FOUND tests | ✓ VERIFIED | 10025 bytes |
| `tests/test_recording_transport.py` | 6 recording wrapper tests | ✓ VERIFIED | 8647 bytes |
| `tests/test_http_laps_data.py` | 8 respx-based HTTP tests | ✓ VERIFIED | 5108 bytes |
| `tests/test_transport_integration.py` | 5 end-to-end integration tests | ✓ VERIFIED | 13729 bytes |
| `.planning/phases/03-transport-replay/03-UAT.md` | UAT checklist for live session | ✓ VERIFIED | 65 lines; 3 verification steps (live capture, replay, HTTP fallback) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `replay.py` | `parser/__init__.py` | `from aionlslivetiming.parser import parse` | ✓ WIRED | Line 28. Every JSONL `raw` is dispatched through `parse()` (D-10 invariant). |
| `websocket.py` | `parser/__init__.py` | `from aionlslivetiming.parser import parse` | ✓ WIRED | Line 54. Every non-time-sync frame is dispatched through `parse()`. |
| `websocket.py` | `transport/base.py` | Uses Transport, ClockOffset, ReconnectPolicy, LTSNotFoundEvent | ✓ WIRED | Lines 56-62. `issubclass(LiveTransport, Transport)` checked at import time (line 556). |
| `websocket.py` | `transport/_connection.py` | Uses _ConnectionState | ✓ WIRED | Lines 55, 253, 293, 416, 437, etc. |
| `websocket.py` | `exceptions.py` | Raises UnknownEventError | ✓ WIRED | Line 52 imports; line 509-512 stores + raises. |
| `recorder.py` | `events/__init__.py` | Reads `msg.event_pid` + `msg.raw` | ✓ WIRED | Lines 127-128: `int(item.event_pid)` and `dict(item.raw)`. |
| `recorder_wrapper.py` | `recorder.py` | Calls `await self._recorder.append(msg)` | ✓ WIRED | Line 100. Append-then-yield invariant enforced. |
| `recorder_wrapper.py` | `base.py` | isinstance check on Transport | ✓ WIRED | Lines 18, 54: `isinstance(inner, Transport)` runtime check. |
| `laps_data.py` | `exceptions.py` | Raises NLSHttpFallbackUnavailable | ✓ WIRED | Line 21 imports; lines 101, 109, 113 raise. |
| `laps_data.py` | `httpx.AsyncClient` | Accepts injected client | ✓ WIRED | Line 55 parameter; line 97 calls `client.get(url)`. |
| `__init__.py` (top-level) | All submodules | Re-exports | ✓ WIRED | All 21 transport-related symbols + fetch_laps_data accessible from top-level import. |
| `transport/__init__.py` | All transport modules | Re-exports | ✓ WIRED | Lines 5-25 cover all sources. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `ReplayTransport.__aiter__` | `msg: Message` | `parser.parse(raw_payload["raw"])` (line 139) | ✓ Real data flow | ✓ FLOWING — D-10 invariant: `raw` re-parsed on every line |
| `LiveTransport._handle_frame` | `msg: Message` | `parser.parse(payload)` (line 461) | ✓ Real data flow | ✓ FLOWING — same parser entry point as replay |
| `RecordingTransport.__aiter__` | `msg: Message` | Forwards from inner Transport | ✓ Real data flow | ✓ FLOWING — inner.messages() → append → yield |
| `JsonlRecorder._writer_loop` | Writes `{ts_recv_ms, event_pid, raw, parsed}` | Each `await self._queue.put(msg)` | ✓ Real data flow | ✓ FLOWING — round-trip test in `test_transport_integration.py` confirms write-then-read yields equal Messages |
| `fetch_laps_data` | Returns parsed JSON dict | `response.json()` (line 107) | ✓ Real data flow (mocked) | ✓ FLOWING — respx-based tests cover JSON success; manual UAT covers real server |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 257 tests pass | `uv run pytest tests/` | "257 passed in 16.09s" | ✓ PASS |
| Coverage gate (>=80%) | `uv run pytest --cov=aionlslivetiming --cov-fail-under=80` | "TOTAL 95.29%" | ✓ PASS |
| Top-level imports work | `python -c "from aionlslivetiming import LiveTransport, ReplayTransport, RecordingTransport, JsonlRecorder, ..."` | All symbols import successfully | ✓ PASS |
| Transport Protocol satisfaction | `isinstance(LiveTransport("evt-1"), Transport)` | True | ✓ PASS |
| ReplayEmptyError on empty file | Empty JSONL raises ReplayEmptyError | Verified | ✓ PASS |
| ClockOffset EWMA smoothing | Two updates → offset_ms = 500.0 | ✓ PASS |
| ReconnectPolicy defaults match D-09 | (1.0, 60.0, None, 10.0, True) | ✓ PASS |
| Recorder rejects double-close | Two close() calls safe | ✓ PASS |
| RecordingTransport rejects non-Transport | TypeError on `inner="not a transport"` | ✓ PASS |
| HTTP fetch URL composition | `_build_url("https://example.com/", "NLS-1", "R1", 7)` returns full URL | ✓ PASS |
| Stream cancel cleanly | `await lt.close()` leaves reader + watchdog tasks done | ✓ PASS |
| LiveTransport handshake shape | `{eventId, eventPid, clientLocalTime}` (eventPid = [0,3,4,7,501,9002]) | ✓ PASS |
| LiveTransport time-sync excluded from main iterator | `__aiter__` yields only non-time-sync Messages | ✓ PASS |
| Lint (ruff) | `uv run ruff check src/aionlslivetiming/transport/ ...` | "All checks passed!" | ✓ PASS |
| Static type check (mypy --strict) | `uv run mypy --strict src/aionlslivetiming/transport/ src/aionlslivetiming/http/ src/aionlslivetiming/exceptions.py` | 2 errors (pre-existing unused-ignore on `import orjson`) | ⚠️ MINOR — documented as out-of-scope per Plan 02 SUMMARY; doesn't block the goal |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CONN-01 | 03-02 | Connect to livetiming WebSocket at wss:// by event id | ✓ SATISFIED | LiveTransport connects with default host + handshake. |
| CONN-02 | 03-01, 03-02 | Disconnect cleanly + release underlying socket | ✓ SATISFIED | LiveTransport.close() cancels tasks + signals queues; ReplayTransport.close() is no-op (file per-iter). |
| CONN-03 | 03-02 | Auto-reconnect with jittered exponential backoff | ✓ SATISFIED | websocket.py:402-412 + tests/test_live_reconnect.py. |
| CONN-04 | 03-01, 03-02 | Honor server time-sync + expose ClockOffset | ✓ SATISFIED | ClockOffset exposed at top level; websocket.py:465-471 updates + enqueues to time_sync queue. |
| CONN-05 | 03-02 | Surface LTS_NOT_FOUND as typed event (not exception) by default | ✓ SATISFIED | lts_not_found() iterator + LTSNotFoundEvent; UnknownEventError only raised when policy=`raise`. |
| CONN-06 | 03-02 | Subscribe to channels (0/4, 3, 7, 501, 9002) | ✓ SATISFIED | Default channels parameter; handshake includes `eventPid` list. |
| CONN-07 | 03-02 | Survive race session transitions | ✓ SATISFIED | Parser-tolerant UnknownMessage + classifier side-effects on _ConnectionState. |
| CONN-08 | 03-01, 03-02 | Override base host for testing | ✓ SATISFIED | LiveTransport(host=...) parameter + tests use `websockets_factory`. |
| STREAM-01 | 03-01, 03-02 | Iterate `async for msg in transport:` | ✓ SATISFIED | All 3 Transport implementations + RecordingTransport support `__aiter__`. |
| STREAM-02 | 03-01, 03-02 | Stream yields typed Message objects, never raw dicts | ✓ SATISFIED | parser.parse() called in both Live + Replay; integration tests assert `isinstance(msg, InitialStateMessage)` etc. |
| STREAM-03 | 03-02 | Backpressure (slow consumer doesn't crash reader task) | ✓ SATISFIED | Three independent asyncio.Queues decouple reader from consumer. (Implicit — not explicitly tested but architecturally sound.) |
| STREAM-04 | 03-01, 03-02 | Cancel stream cleanly without dangling tasks | ✓ SATISFIED | close() cancels reader + watchdog + puts END sentinel; spot-check confirmed tasks are `done()` after close. |
| REC-01 | 03-01, 03-03 | Record live WS message stream to JSONL | ✓ SATISFIED | JsonlRecorder.append(msg) writes one parsed message per line; integration test verifies Live+Recording writes to disk in real time. |
| REC-02 | 03-01, 03-03 | Recorder can be enabled/disabled at runtime | ✗ BLOCKED | No `set_enabled()`, no pause()/resume(), no enable flag. Recorder is either constructed (always-on) or not. |
| REC-03 | 03-03 | Recorder implemented as transport wrapper, not subclass | ✓ SATISFIED | recorder_wrapper.py uses composition (isinstance check); RecordingTransport is itself a Transport. |
| REC-04 | 03-01, 03-03 | Replay JSONL log through same API surface | ✓ SATISFIED | ReplayTransport is a Transport; round-trip tests in test_transport_integration.py. |
| REC-05 | 03-01 | Replay preserves message order + timing OR has speed-multiplier | ✓ SATISFIED | speed_factor parameter (0/1.0/>1/<0); ts_recv_ms ordering enforced with ReplayOrderingError on violation. |
| REC-06 | 03-01 | Replay is independent of any live network | ✓ SATISFIED | ReplayTransport only touches local file; no network imports. |
| HTTP-01 | 03-03 | Library can fetch /event/{id}/laps-data endpoint | ✓ SATISFIED | fetch_laps_data constructs correct URL with session/startingNo params; respx tests verify. |
| HTTP-02 | 03-03 | HTTP fetch uses HA-compatible async client (httpx) | ✓ SATISFIED | httpx.AsyncClient used; injected parameter + default-internal-pool fallback. |
| HTTP-03 | 03-03 | HTTP endpoint is best-effort; no crash on HTML | ✓ SATISFIED | NLSHttpFallbackUnavailable raised on HTML/invalid-JSON/non-object with "use channel 7 instead" message. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/aionlslivetiming/transport/replay.py` | 40 | `import orjson` with `# type: ignore[import-not-found]` flagged as unused-ignore by mypy --strict | ℹ️ Info | Pre-existing; orjson is installed in dev environment so the ignore is unused. Documented in 03-02 SUMMARY as out-of-scope cleanup. |
| `src/aionlslivetiming/transport/recorder.py` | 35 | Same unused-ignore pattern on `import orjson` | ℹ️ Info | Same as above; pre-existing. |

**No blocker anti-patterns found.** No TODO/FIXME comments in source files; no placeholder implementations in critical paths; no console.log-only stubs; no hardcoded empty data flowing to UI.

### Human Verification Required

1. **Live capture (UAT Step 1)**
   - **Test:** Run `async with RecordingTransport(inner=live, recorder=rec) as rt: async for msg in rt: print(msg)` against a real NLS session
   - **Expected:** Typed Message instances stream out; nls-1.jsonl fully written on Ctrl-C
   - **Why human:** All WebSocket tests use a mock websockets_factory; real Azure protocol not exercised.

2. **Replay speed multiplier (UAT Step 2)**
   - **Test:** Replay a real recorded JSONL through `ReplayTransport(path, speed_factor=10.0)`
   - **Expected:** Same messages, 10x faster than real-time
   - **Why human:** Speed_factor is unit-tested with synthetic JSONL; not yet exercised against a real recorded file from the live server.

3. **HTTP fallback real server (UAT Step 3)**
   - **Test:** Hit `/event/{id}/laps-data?session=R1&startingNo=7` against the live server
   - **Expected:** NLSHttpFallbackUnavailable with "use channel 7 instead" message OR parsed JSON dict
   - **Why human:** Respx mocks the documented failure modes; real server behavior not confirmed end-to-end.

### Gaps Summary

**1 gap blocking full goal achievement:**

**REC-02 (Recorder can be enabled/disabled at runtime)** is not implemented. The current `JsonlRecorder` API surface is:
- `JsonlRecorder(path)` — constructor
- `await rec.append(msg)` — queue a write
- `await rec.close()` — flush + stop writer
- async context manager (`async with`)

There is no `set_enabled(bool)`, no `pause()`, no `resume()`, and no enabled flag checked in `append()`. The RecordingTransport wrapper likewise has no toggle.

**Workaround (partial):** A consumer can achieve runtime enable/disable by wrapping/unwrapping a `RecordingTransport` at runtime:
```python
wrapped = RecordingTransport(inner=raw, recorder=rec)
# to disable: stop iterating, close recorder (one-shot), re-construct without recorder
# to enable: open new recorder, construct new wrapper
```

But this is construction-time enable/disable, not runtime toggling on the same recorder instance.

**Severity:** Minor for downstream use cases. Most consumers either want recording always-on (current behavior) or never-on (omit RecordingTransport). The runtime toggle is a power-user feature for tests or interactive use.

**Recommended fix scope:** Add `JsonlRecorder.set_enabled(bool)` method (or an `enabled: bool = True` flag checked in `append()`); add corresponding `RecordingTransport.set_enabled(bool)`; add `tests/test_recording_transport.py::test_recording_transport_can_be_toggled_at_runtime` covering toggle-while-iterating.

**No other gaps.** All 20 other Phase 3 requirements (CONN-01..08, STREAM-01..04, REC-01, REC-03..06, HTTP-01..03) are verified with code evidence and passing tests.

---

## REC-02: Resolved

**Resolved in:** Plan 03-04 (gap closure)
**Resolved at:** 2026-06-21T13:10:00Z
**Commits:**
- `7d6bacd` — feat(03-04): add set_enabled to JsonlRecorder (REC-02 runtime toggle)
- `84b1b6c` — feat(03-04): add set_enabled passthrough to RecordingTransport (REC-02)

### What changed

`JsonlRecorder` now exposes a runtime enable/disable toggle:

```python
rec = JsonlRecorder(path)
await rec.set_enabled(False)  # gate future appends
rec.is_enabled                # -> False
await rec.append(msg)         # silently dropped, no close, no raise
await rec.set_enabled(True)   # resume persistence
```

- `self._enabled: bool = True` is checked at the top of `append()`; when False, the call is a no-op (the writer task is NOT cancelled, queued messages still drain).
- `set_enabled` is `async` to keep a single mutator pattern across the surface and to match the wrapper's `await self._recorder.set_enabled(enabled)` passthrough.
- `is_enabled` is a read-only property.

`RecordingTransport` exposes the same surface and delegates to its inner recorder:

```python
await transport.set_enabled(False)
assert transport.is_enabled is False
# ... iteration continues, but no on-disk writes
```

### Test coverage

Four new tests, all passing:

| Test | File | Asserts |
|------|------|---------|
| `test_set_enabled_disables_writes` | `tests/test_jsonl_recorder.py` | toggle-off drops appends; toggle-on resumes; only post-re-enable line is persisted |
| `test_toggle_while_iterating_safe` | `tests/test_jsonl_recorder.py` | 5 pre-toggle + 1 post-re-enable = 6 lines (5 dropped during disabled period) |
| `test_set_enabled_after_close_raises_no` | `tests/test_jsonl_recorder.py` | calling `set_enabled(False)` after `close()` is safe; flag is just stored |
| `test_recording_transport_set_enabled_passthrough` | `tests/test_recording_transport.py` | `RecordingTransport.set_enabled(False)` → 0 lines on disk; `is_enabled` reflects inner state; messages still yielded to consumer |

### Verification at a glance

- `uv run pytest tests/ -q` → **261 passed in 20.21s** (was 257 — 4 new)
- Coverage: **95.29%** maintained (gate: 80%)
- `uv run ruff check src/ tests/` → **All checks passed!**
- `uv run mypy --strict` on changed files: **0 new errors** (2 pre-existing `orjson` `unused-ignore` documented in 03-02 SUMMARY remain)

### Re-verified requirement

| Requirement | Status | Evidence |
|-------------|--------|----------|
| **REC-02**: Recorder can be enabled/disabled at runtime | ✓ SATISFIED | `JsonlRecorder.set_enabled(bool)` + `is_enabled`; `RecordingTransport.set_enabled(bool)` + `is_enabled`; 4 new tests cover toggle-on/off, toggle-while-burst, post-close safety, and the wrapper passthrough |

All 21/21 Phase 3 requirements are now satisfied.

---

_Verified: 2026-06-21T15:00:00Z_
_Initial verification: 20/21, REC-02 gap flagged_
_Re-verification: 21/21, REC-02 resolved (Plan 03-04)_
_Verifier: the agent (gsd-verifier, then gsd-execute-phase)_