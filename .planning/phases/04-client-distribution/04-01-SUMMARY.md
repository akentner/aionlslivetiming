---
phase: 04-client-distribution
plan: 01
subsystem: client
tags: [composition-root, nlsclient, exception-hierarchy, replay, live, async-context-manager, type-strict]

# Dependency graph
requires:
  - phase: 03-transport-replay
    provides: Transport Protocol, LiveTransport, ReplayTransport, RecordingTransport, JsonlRecorder, ClockOffset, LTSNotFoundEvent/Policy, exceptions preliminary hierarchy, ReconnectPolicy
  - phase: 02-state-filtering
    provides: RaceState with idempotent apply(), Source enum (LIVE/REPLAY/IMPORTED), Freshness enum, state.to_json/from_json
  - phase: 01-foundation-package-parser
    provides: parser.parse() dispatcher, typed Message events, pyproject.toml layout, hatchling build
provides:
  - NLSClient composition root (D-06..D-12): constructor + from_replay classmethod + async iterators + accessors
  - Finalized exception hierarchy (D-23): LTSNotFoundError, ParseError added; UnknownEventError re-purposed for --strict mode
  - LiveTransport raises LTSNotFoundError (not UnknownEventError) for unknown_event classification (D-24)
  - Re-exports: NLSClient at package root; LTSNotFoundError/ParseError at root and transport subpackage
affects:
  - phase: 04-client-distribution (Plans 02-05) — NLSClient is the canonical entry point for CLI, examples, docs
  - phase: 05 (if any) — downstream HA integration wrapper

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Composition-root pattern (NLSClient wires Transport + State; never subclasses)
    - get_state.default_factory for defensive optional methods on Transport Protocol
    - Async-context-manager lifecycle with suppress(CancelledError) in __aexit__ for safe cancellation
    - Tests use a stub Transport that pre-loads messages — hermetic, no live WS

key-files:
  created:
    - src/aionlslivetiming/client.py — NLSClient class (D-06..D-12)
    - tests/test_client.py — 22 unit tests covering construction, iterators, lifecycle, cancellation
  modified:
    - src/aionlslivetiming/exceptions.py — added LTSNotFoundError, ParseError; updated UnknownEventError docstring
    - src/aionlslivetiming/transport/websocket.py — _handle_lts_not_found now raises LTSNotFoundError; reader_loop except clause updated
    - src/aionlslivetiming/__init__.py — re-exports NLSClient, LTSNotFoundError, ParseError
    - src/aionlslivetiming/transport/__init__.py — re-exports LTSNotFoundError, ParseError
    - tests/test_exceptions.py — 10 new tests covering LTSNotFoundError, ParseError, re-purposed UnknownEventError
    - tests/test_lts_not_found.py — renamed import to LTSNotFoundError; added explicit "raises LTSNotFoundError, NOT UnknownEventError" test

key-decisions:
  - "LTSNotFoundError carries (reason, event_id) — events (soft) and errors (loud) are distinct (D-23)"
  - "ParseError carries (event_pid, line_no, message) — only raised by --strict CLI mode (D-23)"
  - "UnknownEventError repurposed: --strict mode surfaces UnknownMessage as UnknownEventError (D-23); LTS_NOT_FOUND uses the dedicated LTSNotFoundError"
  - "NLSClient.infer_source() picks LIVE/REPLAY from concrete transport class via isinstance; RecordingTransport wrapping LiveTransport is LIVE; user-supplied RaceState(source=IMPORTED) wins"
  - "NLSClient.__aexit__ swallows CancelledError so cancellation propagates cleanly per Pitfall #8 (cancellation safety)"
  - "time_sync() and lts_not_found() yield-nothing when transport lacks the method (defensive getattr pattern)"

patterns-established:
  - "Composition root pattern: client.py owns Transport + State; never subclasses"
  - "Defensive getattr() for optional Transport methods (time_sync, lts_not_found, clock_offset)"
  - "Re-export new public symbols from both root __init__.py and subpackage __init__.py"
  - "TDD with stub-Transport pattern for hermetic client tests (no live WS / no real recording)"

requirements-completed: [DIST-04]

# Metrics
duration: ~12min
completed: 2026-06-21
---

# Phase 4 Plan 01: NLSClient Composition Root + Exception Hierarchy Summary

**NLSClient composition root wires Transport -> RaceState with three async iterators and cancellation-safe lifecycle; exception hierarchy finalized with LTSNotFoundError and ParseError (D-23/D-24) and re-purposed UnknownEventError for --strict mode.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-21T13:50:00Z
- **Completed:** 2026-06-21T14:05:00Z
- **Tasks:** 2 (1 sequential auto + 1 TDD with red→green)
- **Files modified:** 8

## Accomplishments

- `NLSClient` is now importable from `aionlslivetiming` and supports the canonical `async with NLSClient(event_id="20") as c: async for msg in c.messages():` flow for both live (LiveTransport under the hood) and replay (`NLSClient.from_replay(path)` wraps a ReplayTransport).
- `RaceState.apply(msg)` runs automatically before each message is yielded by `messages()` (D-08). The state is exposed read-only as `client.state`; `client.source` reflects LIVE/REPLAY/IMPORTED.
- The three-iterator surface (`messages()`, `time_sync()`, `lts_not_found()`) per Phase 3 D-04 + Phase 4 D-10 is unified on the client: `time_sync()` and `lts_not_found()` gracefully yield-nothing when the wrapped transport lacks the method (e.g., `ReplayTransport` has no `lts_not_found()`).
- `__aexit__` swallows `CancelledError` so cancellation completes cleanly within ~1 s (Pitfall #8). Verified with a custom slow-stub test that races a consumer against a 1-second timeout.
- `record_to=` kwarg one-liner composes `RecordingTransport(LiveTransport, JsonlRecorder(path))` per REC-03; `state=RaceState(source=Source.IMPORTED)` is the power-user escape hatch for pre-loaded state.
- Exception hierarchy finalized: `LTSNotFoundError(reason, event_id)` carries the LTS_NOT_FOUND classification (D-23); `ParseError(event_pid, line_no, message)` is reserved for `--strict` CLI mode; `UnknownEventError` is re-purposed for `--strict` UnknownMessage surfacing. `LiveTransport._handle_lts_not_found` now raises `LTSNotFoundError` (not `UnknownEventError`) when policy says `'raise'`.
- The package has zero `homeassistant.*` imports in `src/` (DIST-04). Invariant checked via `grep -rn "^from homeassistant\|^import homeassistant" src/`.
- Test count: 261 → 293 (+32 new tests: 10 exception + 1 LTS-rename + 22 client). No regressions.

## Task Commits

Each task was committed atomically:

1. **Task 1: Finalize exception hierarchy + update transport raise site** — `f02d80a` (feat)
2. **Task 2: Build NLSClient composition root (TDD)** — `4d3ae7d` (feat)

## Files Created/Modified

- `src/aionlslivetiming/client.py` (NEW, 276 lines) — `NLSClient` class per D-06..D-12; composition root
- `tests/test_client.py` (NEW, 415 lines) — 22 tests using a `StubTransport` for hermetic iteration tests
- `src/aionlslivetiming/exceptions.py` — Added `LTSNotFoundError` and `ParseError`; updated `UnknownEventError` docstring per D-23
- `src/aionlslivetiming/transport/websocket.py` — `from aionlslivetiming.exceptions import LTSNotFoundError`; `__aexit__`-style `except LTSNotFoundError` in reader_loop; `UnknownEventError(...)` replaced with `LTSNotFoundError(reason="unknown_event", event_id=...)` in `_handle_lts_not_found`
- `src/aionlslivetiming/__init__.py` — Re-exports `NLSClient`, `LTSNotFoundError`, `ParseError`
- `src/aionlslivetiming/transport/__init__.py` — Re-exports `LTSNotFoundError`, `ParseError`
- `tests/test_exceptions.py` — Extended with 10 new tests covering LTSNotFoundError, ParseError, docstring re-purpose, exports
- `tests/test_lts_not_found.py` — Updated import (UnknownEventError → LTSNotFoundError); added explicit `test_unknown_event_raises_lts_not_found_error_not_unknown_event_error` test

## Decisions Made

- **`LTSNotFoundError` accepts `reason: LTSNotFoundReason | str`** so the type accepts the literal three-state union without breaking callers that pass the string form. Stored on `self.reason`/`self.event_id` for diagnostics.
- **`ParseError.message` is composed with line_no prefix** when `line_no is not None` for log-friendly output; both attributes are stored on the instance.
- **`UnknownEventError` docstring re-purposed** to clearly mark it as the `--strict` mode signal (D-23). The class is kept (not removed) so any caller still catching it works as before.
- **`NLSClient._infer_source()` uses `isinstance`** against the three first-party transport classes. `RecordingTransport` wrapping a `LiveTransport` is `LIVE`; `RecordingTransport` wrapping a `ReplayTransport` is degenerate (returns `REPLAY` via the ReplayTransport check first). Custom transports fall back to `LIVE`.
- **`__aexit__` uses `contextlib.suppress(asyncio.CancelledError)`** — never propagates the cancellation out of the context manager. The transport's own `close()` already cancels its reader task (per Phase 3), so this is the single point of cleanup.
- **Stub transport pattern** for client tests — the tests use a tiny `StubTransport` (satisfies the `Transport` Protocol) with pre-loaded messages so the suite stays hermetic. The end-to-end from_replay test uses a small JSONL written to `/tmp`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed `LTSNotFoundPolicy` import location**
- **Found during:** Task 2 (NLSClient implementation)
- **Issue:** Imported `LTSNotFoundPolicy` from `aionlslivetiming.transport.base` per the plan's interfaces block, but it actually lives in `aionlslivetiming.transport.websocket` (alongside `LiveTransport`).
- **Fix:** Updated the import to `from aionlslivetiming.transport.websocket import LiveTransport, LTSNotFoundPolicy`.
- **Files modified:** `src/aionlslivetiming/client.py`
- **Verification:** `uv run mypy --strict src/aionlslivetiming/client.py` passes; client tests run.
- **Committed in:** `4d3ae7d` (Task 2 commit)

**2. [Rule 2 - Missing Critical] Stub transport helper needs time_sync_msgs and lts_events kwargs**
- **Found during:** Task 2 (TDD RED phase, test_time_sync_delegates_when_transport_supports_it)
- **Issue:** The plan's `_stub_with` helper only accepted `messages=`; tests for the side iterators need to pass `time_sync_msgs` and `lts_events`. Without this, the iterator delegation tests cannot run.
- **Fix:** Extended the helper to accept all three kwargs and forward them to `StubTransport.__init__`.
- **Files modified:** `tests/test_client.py`
- **Verification:** 22 tests pass.
- **Committed in:** `4d3ae7d` (Task 2 commit)

**3. [Rule 3 - Blocking] `UnknownMessage` constructor requires `event_pid` argument**
- **Found during:** Task 2 (TDD, cancellation test uses UnknownMessage)
- **Issue:** `UnknownMessage(event_pid, raw)` — `event_pid` is a required positional arg (instance field, not ClassVar) per `src/aionlslivetiming/events/unknown.py`. Initial test code used `UnknownMessage(raw=...)` which failed at runtime.
- **Fix:** Pass `event_pid=9999` explicitly in the slow-stub generator.
- **Files modified:** `tests/test_client.py`
- **Verification:** Cancellation test passes.
- **Committed in:** `4d3ae7d` (Task 2 commit)

**4. [Rule 2 - Missing Critical] `clock_offset` property uses getattr+cast**
- **Found during:** Task 2 (mypy --strict on client.py)
- **Issue:** The `Transport` Protocol declares only `connect/close/__aiter__`; first-party transports also expose `clock_offset` but mypy treats the attribute as `Any`. Returning `Any` from a property typed `ClockOffset` fails strict typecheck.
- **Fix:** Use `getattr(self._transport, "clock_offset", None)` and `cast("ClockOffset", co)` so the property never raises (defensive default `ClockOffset()` for user-supplied transports that lack it) while satisfying mypy.
- **Files modified:** `src/aionlslivetiming/client.py`
- **Verification:** `uv run mypy --strict src/aionlslivetiming/client.py` passes.
- **Committed in:** `4d3ae7d` (Task 2 commit)

---

**Total deviations:** 4 auto-fixed (4 blocking, 0 missing-critical by plan's definition; items 2 and 4 are correctness-enabling and were applied per Rule 2/3).
**Impact on plan:** All auto-fixes necessary for tests/mypy to pass. No scope creep — every deviation matches the plan's intent and only fixes the literal blocker.

## Issues Encountered

- **Cleanup of stale fragments in client.py during initial write**: The initial implementation left two duplicate fragments (an `if isinstance` block after `__all__`) when the `asyncio_CancelledError()` wrapper was deleted. The first mypy run caught the `IndentationError` on line 263. Fixed by removing the leftover code.
- **`__init__.py` `__all__` edit didn't match exactly**: The plan-style edit pattern (`# fmt: skip` suffix) didn't match the actual file (no fmt skip present). Fixed by rewriting the whole `__init__.py` cleanly with the new symbols.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `NLSClient` is the canonical entry point. Plan 02 (CLI scripts: `nls-record`, `nls-replay`) can build directly on it.
- Plan 03 (worked examples) can import `NLSClient` and `NLSClient.from_replay` from the package root.
- Plan 04 (documentation: mkdocs + README) can reference `NLSClient` as the public API surface.
- Plan 05 (PyPI publish prep) can run `uv build` against the now-finalized public surface.
- The `--strict` mode (Plan 02) can raise `UnknownEventError`/`ParseError` from `aionlslivetiming`; both are exported.

## Self-Check

- [x] `src/aionlslivetiming/client.py` exists and contains `class NLSClient` (276 lines, ≥150 required).
- [x] `src/aionlslivetiming/exceptions.py` exists and contains `class LTSNotFoundError` and `class ParseError`.
- [x] `tests/test_client.py` exists with 22 tests (≥18 required, ≥200 lines: 415 lines).
- [x] `tests/test_exceptions.py` exists with 17 tests (≥11 required).
- [x] `NLSClient` re-exported from `aionlslivetiming.__init__`.
- [x] `LTSNotFoundError` + `ParseError` re-exported from both `__init__.py` and `transport/__init__.py`.
- [x] Zero `homeassistant.*` imports in `src/` (DIST-04 invariant).
- [x] `ruff check src/aionlslivetiming/ tests/` clean.
- [x] `mypy --strict` clean on `client.py`, `exceptions.py`, `transport/websocket.py`.
- [x] Smoke test: `NLSClient.from_replay(small.jsonl)` + `async for msg in c.messages()` works end-to-end.

## Verification Gates (per plan §verification)

1. **No-HA-imports (DIST-04):** `OK: zero homeassistant imports in src/` ✓
2. **Full test suite:** `293 passed in 19.82s` (was 261; +32 new) ✓
3. **Lint + typecheck:** `All checks passed!` / `Success: no issues found in 3 source files` ✓
4. **client.py coverage:** 91% (≥90% required) ✓
5. **End-to-end smoke:** `python /tmp/smoke.py` → `OK` ✓

---
*Phase: 04-client-distribution*
*Completed: 2026-06-21*
