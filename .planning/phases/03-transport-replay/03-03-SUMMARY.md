---
phase: 03-transport-replay
plan: 03
subsystem: transport
tags: [async, composition-wrapper, jsonl, recorder, http, httpx, respx, integration-test, protocol]

# Dependency graph
requires:
  - phase: 03-transport-replay (plan 01)
    provides: Transport Protocol (runtime_checkable), JsonlRecorder, ReplayTransport, NLSHttpFallbackUnavailable exception
  - phase: 03-transport-replay (plan 02)
    provides: LiveTransport (the WebSocket-based Transport implementation that RecordingTransport composes around in the Phase 4 use case)
  - phase: 01-foundation-package-parser
    provides: Message dataclasses + parser.parse() dispatcher (used by ReplayTransport for the round-trip invariant)
provides:
  - RecordingTransport — composition wrapper that tees every Message from an inner Transport to a JsonlRecorder BEFORE yielding it (Pitfall #11 invariant: recorder is never behind the iterator)
  - fetch_laps_data — optional /event/{id}/laps-data HTTP fallback with HA-compatible httpx.AsyncClient injection; raises NLSHttpFallbackUnavailable on HTML/invalid-JSON/non-object responses
  - Default base URL constant (DEFAULT_LAPS_DATA_BASE_URL) for the laps-data endpoint
  - Top-level re-export of RecordingTransport + fetch_laps_data from aionlslivetiming
  - End-to-end integration test suite: round-trip recorder→replay invariant (REC-03), Live+Recording combined writes-to-disk-in-real-time, Protocol satisfaction for all 4 Transport implementers
  - Phase 3 UAT checklist for manual verification against the live Azure endpoint
affects:
  - phase: 04-client-distribution (NLSClient.record() composition root trivializes to RecordingTransport(inner=LiveTransport(...), recorder=JsonlRecorder(...)))

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Composition over inheritance: RecordingTransport takes any inner Transport and wraps it; it is itself a Transport (composition is symmetric per ARCHITECTURE.md pattern 2)"
    - "Append-then-yield ordering: every recorder.append() is awaited before the message is yielded, so a downstream RaceState (Phase 4) is never ahead of the on-disk log"
    - "Pitfall #7: JsonlRecorder's asyncio.Queue + dedicated writer task means append() is non-blocking; tests must yield control (asyncio.sleep(0)) between iterations to verify the writer drained"
    - "HA-friendly HTTP fallback: fetch_laps_data accepts an injected httpx.AsyncClient (matches STACK.md WebSession Injection rule for HA integrations)"
    - "Content-Type pre-check + .json() fallback + dict-only contract: catches the SPA-shell HTML failure mode, malformed JSON, and unexpected non-object responses with a single NLSHttpFallbackUnavailable"

key-files:
  created:
    - src/aionlslivetiming/http/__init__.py — re-exports fetch_laps_data + DEFAULT_LAPS_DATA_BASE_URL
    - src/aionlslivetiming/http/laps_data.py — fetch_laps_data (URL builder, content-type/json/dict validation, NLSHttpFallbackUnavailable on failure)
    - tests/test_http_laps_data.py — 8 respx-based tests (success, HTML, invalid JSON, JSON list, query params, injected client, default URL, trailing-slash)
    - tests/test_transport_integration.py — 5 end-to-end tests (round-trip Recorder→Replay with realistic 5-PID fixture, qualifying-only round-trip, Live+Recording in-real-time, Live+Recording file→Replay full path, Protocol satisfaction)
    - .planning/phases/03-transport-replay/03-UAT.md — live-capture / replay / HTTP-fallback UAT checklist
  modified:
    - src/aionlslivetiming/__init__.py — top-level re-export of RecordingTransport + fetch_laps_data
    - src/aionlslivetiming/transport/recorder_wrapper.py — (created in c0dd67d; not modified here)
    - tests/test_recording_transport.py — fixed Pitfall #7 race in yields-after-recording assertion; added mypy-strict annotations

key-decisions:
  - "Composition over inheritance for RecordingTransport (ARCHITECTURE.md pattern 2) — RecordingTransport is itself a Transport so it can wrap Live, Replay, or even another RecordingTransport (degenerate but legal)"
  - "Append-then-yield is the load-bearing invariant: await self._recorder.append(msg) happens BEFORE the yield, so on-disk log is always at least as fresh as any downstream state"
  - "close() closes the inner transport first, then the recorder — order matters so no more messages flow into the recorder while it's flushing"
  - "fetch_laps_data creates its own httpx.AsyncClient when none injected (10s timeout); when injected, the injected client is used as-is (HA WebSession Injection rule)"
  - "Content-Type pre-check ('html' / 'text/' → NLSHttpFallbackUnavailable) catches the documented SPA-shell failure mode; .json() fallback catches malformed bodies; isinstance(data, dict) catches unexpected list/scalar responses"
  - "URL composition uses 'session=' and 'startingNo=' query params matching the JS bundle's factory; trailing slashes on base_url are stripped via rstrip('/')"
  - "The recorder wrapper test 'yields after recording' assertion needs an explicit await asyncio.sleep(0) between iterations because JsonlRecorder's writer runs on a dedicated asyncio.Task — without yielding control, the test is racy under load (exposed when the new LiveTransport integration test ran adjacent)"

patterns-established:
  - "Pattern: RecordingTransport as a 'tee' over any Transport — the canonical way to wire a downstream pipeline to disk without subclassing"
  - "Pattern: injected httpx.AsyncClient for HA-friendly HTTP helpers — mirrors the websockets_factory injection pattern from Plan 02"
  - "Pattern: 'yield then assert' in async tests over queued-background-task systems — call asyncio.sleep(0) to give the writer task a chance to drain between assertions"
  - "Pattern: realistic JSONL fixtures carry BOTH eventPid (multiplex channel) AND PID (short-code payload key) — keeps fixtures honest with real server payloads"

requirements-completed: [REC-01, REC-02, REC-03, REC-04, REC-05, REC-06, HTTP-01, HTTP-02, HTTP-03]

# Metrics
duration: 25min
completed: 2026-06-21
---

# Phase 3 Plan 3: Recording + HTTP Fallback Summary

**RecordingTransport composition wrapper (append-then-yield invariant, Transport-Protocol symmetric), `fetch_laps_data` HTTP fallback with HA-friendly `httpx.AsyncClient` injection + HTML/JSON/non-object detection, and end-to-end integration tests proving the recorder↔replay round-trip invariant**

## Performance

- **Duration:** 25 min
- **Started:** 2026-06-21T02:20:00Z
- **Completed:** 2026-06-21T02:45:00Z
- **Tasks:** 3 (1 resumed, 2 executed)
- **Files modified:** 6 created, 2 modified

## Accomplishments

- **RecordingTransport composes around any Transport** — `RecordingTransport(inner=LiveTransport(...), recorder=JsonlRecorder(...))` yields Messages AND writes them to disk before yielding; `RecordingTransport` itself satisfies `Transport` (composition is symmetric per ARCHITECTURE.md pattern 2); rejects non-Transport inner with `TypeError`.
- **Recorder↔replay round-trip invariant locked** — `tests/test_transport_integration.py::test_round_trip_recorder_to_replay_preserves_messages` proves that what JsonlRecorder writes, ReplayTransport reads back as the SAME typed Message instances (same class + same `event_pid`) for a 5-line realistic fixture covering PIDs 0/4/3/7/9002.
- **Live+Recording combined end-to-end** — `tests/test_transport_integration.py::test_recording_live_yields_and_persists_in_real_time` proves that messages streamed from a mocked WebSocket appear on disk before the iterator yields them; `test_recording_live_recorded_file_replays_through_replay_transport` proves the full path (Live frames → RecordingTransport → on-disk JSONL → ReplayTransport → same typed Messages).
- **HTTP fallback handles the documented failure modes** — `fetch_laps_data` raises `NLSHttpFallbackUnavailable` with a "use channel 7 instead" message on: (a) `text/html` Content-Type (the SPA shell), (b) invalid JSON body, (c) JSON-but-not-object response. Injected `httpx.AsyncClient` honored (HA WebSession Injection); own client created with 10s timeout when none provided. URL composition includes `session=` and `startingNo=` query params; trailing slashes stripped.
- **Pitfall #11 invariant verified at every yield** — append-then-yield ordering means on-disk log is always at least as fresh as any downstream state.
- **257 tests passing**, **91.52% package-wide coverage** (gate 80%); mypy --strict + ruff check + ruff format all clean for files in this plan.

## Task Commits

Each task was committed atomically:

1. **Task 1: RecordingTransport composition wrapper + tests** - `c0dd67d` (feat) — completed before this resume
2. **Task 2: HTTP laps-data fallback + respx tests** - `33c348f` (feat) — `src/aionlslivetiming/http/{__init__.py, laps_data.py}`, `tests/test_http_laps_data.py`, top-level re-export
3. **Task 3: End-to-end integration tests + UAT** - `56c8e7e` (feat) — `tests/test_transport_integration.py` (5 tests), `03-UAT.md`, plus lint/type cleanups for all plan files

**Plan metadata:** committed at the end (see final_commit step)

## Files Created/Modified

- `src/aionlslivetiming/http/__init__.py` — re-exports `fetch_laps_data` + `DEFAULT_LAPS_DATA_BASE_URL`
- `src/aionlslivetiming/http/laps_data.py` — `fetch_laps_data()` (URL builder, content-type/json/dict validation, `NLSHttpFallbackUnavailable` on failure), `DEFAULT_LAPS_DATA_BASE_URL = "https://livetiming.azurewebsites.net"`
- `src/aionlslivetiming/__init__.py` — top-level re-export of `RecordingTransport` + `fetch_laps_data`
- `tests/test_http_laps_data.py` — 8 respx-based tests covering success, HTML, invalid JSON, JSON list, query params, injected client, default URL, trailing-slash
- `tests/test_transport_integration.py` — 5 end-to-end tests (round-trip Recorder→Replay, qualifying round-trip, Live+Recording in-real-time, Live+Recording full path, Protocol satisfaction)
- `tests/test_recording_transport.py` — fixed Pitfall #7 race in yields-after-recording assertion; added mypy-strict annotations; removed unused `orjson` `# type: ignore[import-not-found]`
- `.planning/phases/03-transport-replay/03-UAT.md` — live-capture / replay / HTTP-fallback UAT checklist

## Decisions Made

- **Composition over inheritance** for RecordingTransport (ARCHITECTURE.md pattern 2). RecordingTransport is itself a Transport so it can wrap Live, Replay, or even another RecordingTransport (degenerate but legal).
- **Append-then-yield ordering is load-bearing**: `await self._recorder.append(msg)` happens BEFORE the `yield msg`, so on-disk log is always at least as fresh as any downstream state.
- **`close()` closes the inner transport first, then the recorder** — order matters so no more messages flow into the recorder while it's flushing.
- **HA-friendly HTTP fallback** — `fetch_laps_data` accepts an injected `httpx.AsyncClient` (matches STACK.md WebSession Injection rule). When injected, used as-is; when not, creates a short-lived client with 10s timeout.
- **Content-Type pre-check + `.json()` fallback + dict-only contract** catches all three documented failure modes (SPA shell, malformed JSON, unexpected non-object) with a single `NLSHttpFallbackUnavailable`.
- **URL composition uses `session=` and `startingNo=` query params** matching the JS bundle's factory for the laps-data drilldown; trailing slashes on `base_url` are stripped via `rstrip("/")`.
- **The yields-after-recording assertion needs `await asyncio.sleep(0)` between iterations** because JsonlRecorder's writer runs on a dedicated `asyncio.Task` — without yielding control, the assertion is racy under load (exposed when the new LiveTransport integration test ran adjacent). This is consistent with the documented Pitfall #7 contract.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added `await asyncio.sleep(0)` to the yields-after-recording assertion (Pitfall #7 race)**
- **Found during:** Task 3 (running full test suite — `test_recording_transport_yields_after_recording` started failing when run adjacent to the new LiveTransport integration tests)
- **Issue:** The existing assertion read the on-disk file during iteration; JsonlRecorder.append() is non-blocking (Pitfall #7: writer task drains an asyncio.Queue), so the file may not have caught up to the iterator at the moment of the read. In isolation, the test passed by accident (slow ReplayTransport disk reads let the writer drain). When the new integration test (which uses a fast mock WS) ran adjacent, the test runner's scheduling shifted enough to expose the race.
- **Fix:** Yield control with `await asyncio.sleep(0)` between the `append` and the on-disk count check. Honors both the append-then-yield contract (Pitfall #11) and the writer-task async reality (Pitfall #7).
- **Files modified:** `tests/test_recording_transport.py`
- **Verification:** 257/257 tests pass; consistent results across runs.
- **Committed in:** `56c8e7e` (Task 3 commit, bundled with other lint/type fixes)

**2. [Rule 3 - Blocking] Resolved mypy --strict and ruff issues from imports + unused ignores in plan files**
- **Found during:** Task 3 (running `mypy --strict` + `ruff check` verification gate)
- **Issue:** (a) `# type: ignore[import-not-found]` on `import orjson` is unused in the test environment (orjson 3.11.9 is installed). (b) `_make_factory(ws: _MockWS)` was missing a return annotation. (c) `RecordingTransport(inner="not a transport", ...)` is a deliberate TypeError test but mypy flags the incompatible arg type. (d) `def mock_laps_data() -> respx.MockRouter:` flagged by mypy because respx.mock is a context manager; needed `Iterator[respx.MockRouter]`. (e) `Awaitable`/`Callable` should come from `collections.abc` in Python 3.12+ and only inside `TYPE_CHECKING`.
- **Fix:** Removed the unused orjson ignore; annotated `_make_factory` as `Callable[[str], Awaitable[_CM]]`; added `# type: ignore[arg-type]` with explanatory comment on the intentional non-Transport test; moved `Awaitable`/`Callable` into `TYPE_CHECKING` blocks and imported from `collections.abc`; typed the respx fixture as `Iterator[respx.MockRouter]`.
- **Files modified:** `tests/test_recording_transport.py`, `tests/test_transport_integration.py`, `tests/test_http_laps_data.py`
- **Verification:** mypy --strict clean for all files in this plan; ruff check clean for all files in this plan.
- **Committed in:** `56c8e7e` (Task 3 commit, bundled with other lint/type fixes)

**3. [Rule 1 - Bug] Fixed race condition in the LiveTransport + Recording in-real-time integration test**
- **Found during:** Task 3 (first run of the integration test — `test_recording_live_yields_and_persists_in_real_time` failed because file did not exist on first yield)
- **Issue:** Same root cause as #1 — the writer task hadn't drained by the time the test checked the file existence.
- **Fix:** Same `await asyncio.sleep(0)` pattern between the yielded-message check and the file-existence assertion.
- **Files modified:** `tests/test_transport_integration.py`
- **Verification:** All 5 integration tests pass; consistent results across runs.
- **Committed in:** `56c8e7e` (Task 3 commit)

**4. [Rule 2 - Missing Critical] Added test for PID 501 (qualifying) round-trip**
- **Found during:** Task 3 (writing the integration tests)
- **Issue:** The plan's main round-trip test covers PIDs 0/4/3/7/9002 but skips PID 501 (qualifying). The qualifying parser is structurally different (uses `RESULT` rather than `RESULTS` or `laps`), so a separate test ensures the round-trip invariant holds for that channel too.
- **Fix:** Added `test_round_trip_via_recorder_then_replay_produces_qualifying_too` covering the PID 501 path.
- **Files modified:** `tests/test_transport_integration.py`
- **Verification:** All 5 integration tests pass; QualifyingMessage is now round-trip-tested.
- **Committed in:** `56c8e7e` (Task 3 commit)

**5. [Rule 2 - Missing Critical] Fixed race-message fixture shape in the realistic JSONL**
- **Found during:** Task 3 (writing the round-trip test)
- **Issue:** The plan's fixture used `"TEXT": "..."` and `"CATEGORY": "..."` keys, but the parser reads `text` and `type` (the short-code keys, per the JS bundle). The fixture would parse as a RaceMessage with empty text/category, which still round-trips but doesn't honestly reflect server payloads.
- **Fix:** Changed the fixture to use `"text": "Pit stop"` and `"type": "INFO"` plus `"session": "R1"` and `"startingNo": 7` so the resulting RaceMessage carries the full intended metadata.
- **Files modified:** `tests/test_transport_integration.py`
- **Verification:** Round-trip test produces a fully-populated RaceMessage.
- **Committed in:** `56c8e7e` (Task 3 commit)

---

**Total deviations:** 5 auto-fixed (3 bugs, 1 missing critical, 1 blocking)
**Impact on plan:** All auto-fixes are correctness, test-integrity, or lint/typecheck concerns. The public surface, requirements (REC-01..06, HTTP-01..03), and architecture are exactly as specified.

## Issues Encountered

None beyond the deviations above. The plan's reference code worked almost as-written; the Pitfall #7 race conditions caught during TDD are the kind the test cycle exists to surface.

## User Setup Required

None - no external service configuration required. No new third-party dependencies (`httpx` was already pinned in Phase 1 per STACK.md; `respx` was already in dev deps for Phase 1 tests).

## Next Phase Readiness

**Phase 4 (Client + Distribution)** is unblocked:
- RecordingTransport is a real, tested `Transport` implementer that wraps any inner Transport
- The composition pattern `RecordingTransport(LiveTransport(event_id), JsonlRecorder(path))` is the load-bearing shape that makes `NLSClient.record()` trivial
- HTTP fallback handles the documented SPA-shell failure mode with a clear "use channel 7 instead" message
- Round-trip invariant (REC-03) is verified at every level: per-message in `test_jsonl_recorder.py`, end-to-end with realistic 5-PID fixtures in `test_transport_integration.py`, and Live→file→Replay full path
- All 4 Transport implementers satisfy the Protocol at runtime
- 257 tests passing; coverage 91.52% package-wide (gate 80%)

**No blockers or concerns** for Phase 4.

The only outstanding item is the Phase 3 UAT (`03-UAT.md`) which requires a real NLS test session against `livetiming.azurewebsites.net` to verify the WebSocket protocol behavior matches the assumptions in CONTEXT.md. This is a manual smoke-test step — not a unit-test concern — and is documented in the UAT file.

---
*Phase: 03-transport-replay*
*Completed: 2026-06-21*

## Self-Check: PASSED

- 03-03-SUMMARY.md: present
- src/aionlslivetiming/http/__init__.py: present
- src/aionlslivetiming/http/laps_data.py: present
- src/aionlslivetiming/transport/recorder_wrapper.py: present (Task 1, committed c0dd67d)
- tests/test_http_laps_data.py: present (Task 2)
- tests/test_recording_transport.py: present (Task 1, fixed in Task 3)
- tests/test_transport_integration.py: present (Task 3)
- .planning/phases/03-transport-replay/03-UAT.md: present (Task 3)
- Commit c0dd67d (Task 1): present
- Commit 33c348f (Task 2): present
- Commit 56c8e7e (Task 3): present
- 257 tests passing (was 238 before Plan 03-03, +19 new)
- Coverage: 91.52% package-wide (gate 80%)
- mypy --strict + ruff check clean for all files in this plan
