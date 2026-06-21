"""Transport Protocol and shared types (Phase 3 base layer).

Three implementations satisfy :class:`Transport`:
- :class:`aionlslivetiming.transport.replay.ReplayTransport` (Plan 01)
- :class:`aionlslivetiming.transport.websocket.LiveTransport` (Plan 02)
- :class:`aionlslivetiming.transport.recorder.RecordingTransport` (Plan 03, composition wrapper)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from aionlslivetiming.events import Message


@runtime_checkable
class Transport(Protocol):
    """Async stream of parsed :data:`~aionlslivetiming.events.Message` instances.

    Three implementations satisfy this Protocol: ReplayTransport (offline),
    LiveTransport (WebSocket), RecordingTransport (composition wrapper).

    Lifecycle:
        await transport.connect()     # one-shot; idempotent
        async for msg in transport:   # iterate until exhaustion / close
        await transport.close()       # always call in finally

    Time-sync messages (`{type:"time"}`) are NEVER yielded by the default
    `__aiter__`. They are routed to a separate `clock_offset` helper and
    may also appear on a dedicated async iterator (LiveTransport exposes
    `time_sync()`; ReplayTransport exposes them only when
    `suppress_time_sync=False`).
    """

    async def connect(self) -> None:
        """Open the underlying connection / file. Idempotent — calling twice is a no-op."""
        ...

    async def close(self) -> None:
        """Release the underlying connection / file. Idempotent."""
        ...

    def __aiter__(self) -> AsyncIterator[Message]:
        """Yield parsed Message instances (time-sync excluded by default)."""
        ...


# ---- Helper types used by LiveTransport (Plan 02) — declared here so the
#      public surface is stable across the phase ----

LTSNotFoundReason = Literal["not_yet_started", "ended", "unknown_event"]
"""Three-state classification of LTS_NOT_FOUND (D-05..D-07)."""


@dataclass(frozen=True)
class LTSNotFoundEvent:
    """Typed event yielded when the server responds with LTS_NOT_FOUND (D-05).

    Three reasons (D-06):
    - `not_yet_started` — connection is recent and no race has been seen yet; reconnect
    - `ended` — a previous TrackStateMessage had FINISHED/CHEQUERED or a non-empty ENDTIME; terminal
    - `unknown_event` — fallback; consumer decides
    """

    reason: LTSNotFoundReason
    event_id: str
    first_seen_at_ms: int  # server time when LTS_NOT_FOUND was first observed


# ---- Time-sync clock offset (D-04, D-16) ----

@dataclass
class ClockOffset:
    """Tracks the offset between server time and local wall-clock.

    Live: each `{type:"time", value:<ms>}` frame updates this.
    Replay: same, unless `suppress_time_sync=True` (the default).

    The offset is `server_time_ms - local_time_ms_at_recv`. Consumers can read
    `now_server_ms()` to convert a local `time.time() * 1000` to server time.
    """

    _offset_ms: float | None = field(default=None, init=False)

    def update(self, server_time_ms: int, local_recv_ms: int) -> None:
        """Record a new sample. Keeps a rolling EWMA so jitter smooths out."""
        sample = server_time_ms - local_recv_ms
        if self._offset_ms is None:
            self._offset_ms = float(sample)
        else:
            # EWMA alpha = 0.3 — favors recent samples; smooths transient jitter.
            self._offset_ms = 0.7 * self._offset_ms + 0.3 * sample

    def now_server_ms(self) -> int | None:
        """Return the current best estimate of server time in ms (None until first sample)."""
        if self._offset_ms is None:
            return None
        return int(time.time() * 1000 + self._offset_ms)

    @property
    def offset_ms(self) -> float | None:
        """The most recent offset estimate, or None before the first sample."""
        return self._offset_ms


# ---- Reconnect policy (D-09..D-13) ----

@dataclass(frozen=True)
class ReconnectPolicy:
    """Jittered exponential backoff for LiveTransport reconnect.

    Defaults (D-09..D-11):
    - base_delay_s=1.0, cap_delay_s=60.0, max_attempts=None (infinite)
    - initial_offset_s=10.0 (per-process random delay before FIRST attempt)
    - honor_retry_after=True

    Delay formula (D-10): full jitter — `random.uniform(0, min(cap, base * 2**attempt))`.
    `attempt` resets to 0 after a successful connection that ran > 60 s (D-11).
    """

    base_delay_s: float = 1.0
    cap_delay_s: float = 60.0
    max_attempts: int | None = None
    initial_offset_s: float = 10.0
    honor_retry_after: bool = True


__all__ = [
    "ClockOffset",
    "LTSNotFoundEvent",
    "LTSNotFoundReason",
    "ReconnectPolicy",
    "Transport",
]
