# Phase 3: Transport + Replay - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-21
**Phase:** 03-transport-replay
**Areas discussed:** Heartbeat & keepalive, LTS_NOT_FOUND policy, Reconnect backoff curve, Replay speed & time semantics

---

## Heartbeat & keepalive

| Option | Description | Selected |
|--------|-------------|----------|
| App-level heartbeat from time-sync (Recommended) | `ping_interval=None`; synthetic heartbeat from `{type:"time"}`; idle detection on `idle_timeout_s` (default 90 s); time-sync on dedicated `time_sync()` iterator | ✓ |
| Let websockets library handle pings | `ping_interval=20, ping_timeout=20`. Simpler. Risk: unreliable through Azure ARR for the idle-stretch case. | |
| Both: lib pings + app-level fallback | Belt-and-suspenders. More code, more log noise. | |

**User's choice:** App-level heartbeat from time-sync
**Notes:** Azure ARR's documented ~4 min idle timeout is the primary motivator. 90 s default is ~2.5× safety margin.

### Follow-up: close-code policy

| Option | Description | Selected |
|--------|-------------|----------|
| Reconnect on 1006/1011/1012/1013 only (Recommended) | 1006/1011/1012/1013 → reconnect; 1000/1001 → don't; 1005 → treat as 1006 | ✓ |
| Always reconnect | Any close triggers reconnect. Misses intentional server close. | |
| Never reconnect on 1000, do on everything else | Less granular than recommended option. | |

**User's choice:** Reconnect on 1006/1011/1012/1013 only

---

## LTS_NOT_FOUND policy

| Option | Description | Selected |
|--------|-------------|----------|
| Typed event with three states (Recommended) | `LTSNotFoundEvent(reason: Literal["not_yet_started","ended","unknown_event"])` on dedicated iterator; configurable per-reason via `LTSNotFoundPolicy` | ✓ |
| Single event + raise for unknown_event only | One event type; only unknown_event raises. Simpler API. | |
| Raise exception always | Loses pre-race / end-of-session distinction. | |

**User's choice:** Typed event with three states

### Follow-up: three-state classification heuristic

| Option | Description | Selected |
|--------|-------------|----------|
| Best-guess from timing (Recommended) | Stateful classifier using connection age + previously-seen FINISHED/CHEQUERED state. Configurable thresholds. | ✓ |
| Ask the user via config | Consumer classifies post-hoc. Most flexible, most work. | |
| Always unknown_event | Always emit as unknown_event; consumer classifies. | |

**User's choice:** Best-guess from timing

---

## Reconnect backoff curve

| Option | Description | Selected |
|--------|-------------|----------|
| Exponential + full jitter, 1s→60s cap, 0-10s initial offset (Recommended) | `delay = random.uniform(0, min(cap, base * 2**attempt))`; base=1.0s cap=60s max_attempts=None; per-process initial offset `random.uniform(0, 10)` before first attempt; honor `Retry-After` | ✓ |
| Same curve but capped at fewer attempts | max_attempts=10, give up after ~10 min. Risk during long Azure maintenance. | |
| Simpler: fixed jittered delay | `random.uniform(1, 5)` between attempts. Doesn't smooth reconnect waves. | |

**User's choice:** Exponential + full jitter, 1s→60s cap, 0-10s initial offset

---

## Replay speed & time semantics

| Option | Description | Selected |
|--------|-------------|----------|
| speed_factor + time-sync informational (Recommended) | `speed_factor=1.0` default (real-time via asyncio.sleep on ts_recv_ms delta); `speed_factor=0` burst; time-sync informational (updates clock_offset, not yielded unless suppress_time_sync=False) | ✓ |
| Burst by default, speed opt-in | Default `speed_factor=0`. Faster for tests; loses faithful-to-live-timing property. | |
| Real-time only, no speed control | Always real-time using ts_recv_ms deltas. Simplest API. Tests must skip sleep via clock injection. | |

**User's choice:** speed_factor + time-sync informational

### Follow-up: JSONL robustness

| Option | Description | Selected |
|--------|-------------|----------|
| Skip partial lines (warn), enforce monotonic ts_recv_ms (Recommended) | Partial trailing line → WARNING + skip. Out-of-order ts_recv_ms → raise `ReplayOrderingError`. Empty file → `ReplayEmptyError`. Missing `raw` → `ReplaySchemaError`. | ✓ |
| Skip partial lines, lenient ordering | Sort before yielding. Masks upstream recorder bugs. | |
| Strict: any malformed line raises | Maximally safe. A 2am crash loses the whole log. | |

**User's choice:** Skip partial lines (warn), enforce monotonic ts_recv_ms

---

## the agent's Discretion

- Transport sub-package file layout (`transport/base.py`, `websocket.py`, `replay.py`, `recorder.py`)
- `JsonlRecorder` async-isolated writer task via `asyncio.Queue`
- Exact `__repr__` of `LTSNotFoundEvent` / `LTSNotFoundReason` / `ReconnectPolicy`
- Whether `LiveTransport.connect()` returns `self` for chaining
- HTTP fallback: separate `httpx.AsyncClient` per call vs. injected client (HA-friendly default is injected)
- D-EXC exception class shape (deferred to Phase 4 discuss-phase)

---

## Deferred Ideas

- D-EXC exception hierarchy: `NLSError` base + `ConnectionError`/`UnknownEventError`/`ReplayError`+subclasses/`NLSHttpFallbackUnavailable`. Resolve naming at Phase 4.
- HTTP laps-data fallback behavior detail (specific exception shape, "use channel 7 instead" message wording): planner picks sensible defaults.
- File rotation (Pitfall #12): not in Phase 3 scope.
- `clock_offset` public API shape: planner picks simplest synchronous helper.
- CLI entry points, `NLSClient` composition root, PyPI distribution: all Phase 4.
