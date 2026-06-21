"""Live transport — WebSocket consumer for the NLS livetiming feed.

Implements the :class:`~aionlslivetiming.transport.base.Transport` Protocol
over a single multiplexed WebSocket connection to the Azure-hosted NLS
endpoint. Drives application-level keepalive from the server's
``{type:"time"}`` frames, runs jittered exponential backoff on transient
errors (Pitfall #6), and surfaces ``LTS_NOT_FOUND`` as a typed three-state
event (Pitfall #5).

Architecture
------------
Three long-lived components per LiveTransport instance:

- ``_reader_loop`` — outer reconnect loop. Spawns a fresh ``_session_loop``
  per attempt and computes the next backoff delay after each one ends.
- ``_session_loop`` — one connection lifecycle: connect → handshake → frame
  loop → close. The reader task is the only place that talks to the
  ``websockets`` library.
- ``_idle_watchdog`` — independent task that wakes every ``idle_timeout_s/3``
  seconds (capped at 10s) and cancels the reader task if no frame has
  arrived in ``idle_timeout_s`` seconds (D-02).

Three independent async iterators feed from three ``asyncio.Queue``s set
up in ``connect()``:

- ``__aiter__`` / ``messages()`` — parsed Message instances (time-sync excluded per D-04)
- ``time_sync()`` — TimeSyncMessage instances (D-04)
- ``lts_not_found()`` — LTSNotFoundEvent instances (D-05)

The classifier (``_classify_lts_not_found``) runs against an internal
``_ConnectionState`` that observes TrackStateMessages (for the ``ended``
signal) and InitialStateMessages (for the ``seen_initial_state_with_results``
signal used by the D-06 ``not_yet_started`` heuristic).
"""

from __future__ import annotations

import asyncio
import contextlib
import json as _stdlib_json
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Any

from aionlslivetiming.events import (
    InitialStateMessage,
    Message,
    TimeSyncMessage,
    TrackStateMessage,
)
from aionlslivetiming.exceptions import LTSNotFoundError
from aionlslivetiming.logging import get_logger
from aionlslivetiming.parser import parse
from aionlslivetiming.transport._connection import _ConnectionState
from aionlslivetiming.transport.base import (
    ClockOffset,
    LTSNotFoundEvent,
    LTSNotFoundReason,
    ReconnectPolicy,
    Transport,
)

__all__ = ["LTSNotFoundPolicy", "LiveTransport"]

_log = get_logger("aionlslivetiming.transport.websocket")

# Per D-01: do NOT let the websockets library auto-ping; we drive keepalive.
# close_timeout=5 means Azure silent close is detected within ~5s (Pitfall #1).
_WS_OPEN_KWARGS: dict[str, Any] = {
    "ping_interval": None,
    "ping_timeout": None,
    "close_timeout": 5,
    "open_timeout": 10,
    "max_size": 2**20,  # 1 MiB — server frames are tiny; reject pathological sizes early
}

# Per D-03: which close codes trigger a reconnect.
_RECONNECT_CLOSE_CODES: frozenset[int] = frozenset({1006, 1011, 1012, 1013})

# Per D-11: a session that ran for >60s resets the attempt counter to 0.
_SUCCESS_RESET_SECONDS: float = 60.0


def _loads(raw: str | bytes | bytearray) -> Any:
    """JSON decode; orjson if available, stdlib fallback (D-10)."""
    try:
        import orjson

        return orjson.loads(raw)
    except ImportError:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="replace")
        return _stdlib_json.loads(raw)


def _dumps(obj: Any) -> str:
    """JSON encode; orjson if available, stdlib fallback (D-10)."""
    try:
        import orjson

        result: str = orjson.dumps(obj).decode("utf-8")
    except ImportError:
        result = _stdlib_json.dumps(obj, separators=(",", ":"))
    return result


def _default_host() -> str:
    """Lazy import to avoid hard import cycle with ``cli/`` at test time."""
    from aionlslivetiming.cli.jsonl_logger import DEFAULT_HOST

    return DEFAULT_HOST


def _default_channels() -> tuple[int, ...]:
    """Lazy import to avoid hard import cycle with ``cli/`` at test time."""
    from aionlslivetiming.cli.jsonl_logger import DEFAULT_CHANNELS

    return DEFAULT_CHANNELS


# ---- Internal sentinel + sentinel kinds ----


class _SentinelKind:
    """Discriminator for ``_Sentinel`` — distinguishes natural end-of-stream
    (``close()`` was called) from reconnect exhaustion (``max_attempts``
    reached) and ``ended`` LTS_NOT_FOUND classification (D-07)."""

    END = "end"
    EXHAUSTED = "exhausted"


class _Sentinel:
    """Internal queue sentinel used to terminate the async iterators."""

    __slots__ = ("kind",)

    def __init__(self, kind: str = _SentinelKind.END) -> None:
        self.kind = kind


_SENTINEL_END: _Sentinel = _Sentinel(_SentinelKind.END)


class LTSNotFoundPolicy:
    """Per-reason default behaviour for LTS_NOT_FOUND (D-07, D-08).

    Each field is one of:

    - ``"continue"``  — keep trying (backoff loop will reconnect)
    - ``"terminate"`` — stop reconnecting, mark connection ended
    - ``"raise"``     — raise :class:`LTSNotFoundError`

    Defaults match D-07::

        LTSNotFoundPolicy()  # on_not_yet_started="continue",
                             # on_ended="terminate",
                             # on_unknown_event="raise"
    """

    __slots__ = ("on_ended", "on_not_yet_started", "on_unknown_event")

    def __init__(
        self,
        *,
        on_not_yet_started: str = "continue",
        on_ended: str = "terminate",
        on_unknown_event: str = "raise",
    ) -> None:
        for v in (on_not_yet_started, on_ended, on_unknown_event):
            if v not in ("continue", "terminate", "raise"):
                raise ValueError(f"invalid LTS_NOT_FOUND policy value: {v!r}")
        self.on_not_yet_started = on_not_yet_started
        self.on_ended = on_ended
        self.on_unknown_event = on_unknown_event

    def __repr__(self) -> str:
        return (
            f"LTSNotFoundPolicy(on_not_yet_started={self.on_not_yet_started!r}, "
            f"on_ended={self.on_ended!r}, on_unknown_event={self.on_unknown_event!r})"
        )


# Backwards-compat alias (the plan used an underscore-prefixed name internally).
_LTSNotFoundPolicy = LTSNotFoundPolicy


class LiveTransport:
    """Live WebSocket consumer of the NLS livetiming feed.

    Implements :class:`~aionlslivetiming.transport.base.Transport`.
    Reconnect-on-transient with jittered backoff (D-09..D-13). Surfaces
    ``LTS_NOT_FOUND`` as a three-state typed event (D-05..D-08). Drives
    app-level keepalive from the server's ``{type:"time", value:<ms>}``
    frames (D-01..D-02).

    Parameters
    ----------
    event_id:
        Event identifier sent in the initial handshake JSON.
    host:
        WebSocket URL. Defaults to ``wss://livetiming.azurewebsites.net/``.
    channels:
        Channel IDs (``eventPid`` values) to subscribe to. Default
        ``(0, 3, 4, 7, 501, 9002)``.
    reconnect_policy:
        :class:`ReconnectPolicy` instance controlling backoff behaviour.
    idle_timeout_s:
        Force a reconnect if no frame is received for this many seconds
        (D-02). Default 90s — well under Azure's ~4min idle timeout.
    pre_race_threshold_s:
        D-06 ``not_yet_started`` threshold. Default 300s (5 min).
    lts_not_found_policy:
        :class:`LTSNotFoundPolicy` — per-reason default behaviour (D-07, D-08).
    websockets_factory:
        Optional override for ``websockets.connect`` (used in tests).
    """

    def __init__(
        self,
        event_id: str,
        *,
        host: str | None = None,
        channels: Sequence[int] | None = None,
        reconnect_policy: ReconnectPolicy | None = None,
        idle_timeout_s: float = 90.0,
        pre_race_threshold_s: float = 300.0,
        lts_not_found_policy: LTSNotFoundPolicy | None = None,
        websockets_factory: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        self._event_id = str(event_id)
        self._host = host if host is not None else _default_host()
        self._channels: tuple[int, ...] = (
            tuple(channels) if channels is not None else _default_channels()
        )
        self._reconnect_policy = (
            reconnect_policy if reconnect_policy is not None else ReconnectPolicy()
        )
        self._idle_timeout_s = float(idle_timeout_s)
        self._pre_race_threshold_s = float(pre_race_threshold_s)
        self._lts_not_found_policy = (
            lts_not_found_policy if lts_not_found_policy is not None else LTSNotFoundPolicy()
        )
        self._websockets_factory = websockets_factory
        self._clock_offset = ClockOffset()
        self._connected = False
        self._closed = False
        # Queues set up in connect(); sentinel = "no more messages".
        self._messages_q: asyncio.Queue[Message | _Sentinel] | None = None
        self._time_sync_q: asyncio.Queue[TimeSyncMessage | _Sentinel] | None = None
        self._lts_q: asyncio.Queue[LTSNotFoundEvent | _Sentinel] | None = None
        self._state: _ConnectionState | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        # Pending exception to raise on the messages() iterator (D-07 unknown_event).
        # Set by the reader task, read+cleared by the iterator on EXHAUSTED.
        self._pending_messages_exc: BaseException | None = None

    # ---- Public properties ----

    @property
    def clock_offset(self) -> ClockOffset:
        """The clock-offset tracker (D-04)."""
        return self._clock_offset

    @property
    def event_id(self) -> str:
        """The event id passed at construction."""
        return self._event_id

    @property
    def ended(self) -> bool:
        """True if the connection was terminated due to LTS_NOT_FOUND ``ended`` (D-07)."""
        return bool(self._state is not None and self._state.ended_seen)

    # ---- Transport Protocol ----

    async def connect(self) -> None:
        """Start the reader + watchdog tasks. Returns once the queues are wired.

        Does NOT block on the first connection attempt — the actual
        ``websockets.connect`` happens inside the reader task, which also
        owns the reconnect loop.
        """
        if self._connected:
            return
        self._connected = True
        self._closed = False
        self._messages_q = asyncio.Queue()
        self._time_sync_q = asyncio.Queue()
        self._lts_q = asyncio.Queue()
        self._state = _ConnectionState(event_id=self._event_id)
        self._reader_task = asyncio.create_task(self._reader_loop(), name="nls-reader")
        self._watchdog_task = asyncio.create_task(self._idle_watchdog(), name="nls-watchdog")

    async def close(self) -> None:
        """Stop the reader + watchdog tasks. Idempotent."""
        if self._closed:
            return
        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog_task
        # Signal end-of-stream on the queues so async iterators unblock.
        for q in (self._messages_q, self._time_sync_q, self._lts_q):
            if q is not None:
                await q.put(_SENTINEL_END)
        self._connected = False

    def __aiter__(self) -> AsyncIterator[Message]:
        """Yield parsed Message instances (time-sync excluded per D-04)."""
        return self.messages()

    async def messages(self) -> AsyncIterator[Message]:
        """Yield parsed Message instances (time-sync excluded per D-04)."""
        if not self._connected:
            await self.connect()
        assert self._messages_q is not None
        while True:
            item = await self._messages_q.get()
            if isinstance(item, _Sentinel):
                # D-07: re-raise a pending exception (UnknownEventError from
                # unknown_event classification) before terminating.
                exc = self._pending_messages_exc
                self._pending_messages_exc = None
                if exc is not None:
                    raise exc
                return
            # Narrowing: ``item`` is Message here (queue contract), but
            # ``Message`` is a typing.Union which mypy won't accept for
            # isinstance. Trust the contract.
            yield item

    async def time_sync(self) -> AsyncIterator[TimeSyncMessage]:
        """Yield :class:`TimeSyncMessage` instances (D-04 dedicated iterator)."""
        if not self._connected:
            await self.connect()
        assert self._time_sync_q is not None
        while True:
            item = await self._time_sync_q.get()
            if isinstance(item, _Sentinel):
                return
            assert isinstance(item, TimeSyncMessage)
            yield item

    async def lts_not_found(self) -> AsyncIterator[LTSNotFoundEvent]:
        """Yield :class:`LTSNotFoundEvent` instances (D-05)."""
        if not self._connected:
            await self.connect()
        assert self._lts_q is not None
        while True:
            item = await self._lts_q.get()
            if isinstance(item, _Sentinel):
                return
            assert isinstance(item, LTSNotFoundEvent)
            yield item

    # ---- Internal: reader + watchdog loops ----

    async def _reader_loop(self) -> None:
        """Outer reconnect loop. Spawns inner :meth:`_session_loop`; handles backoff."""
        attempt = 0
        if self._reconnect_policy.initial_offset_s > 0:
            # Per-process random initial offset (D-11) — first-attempt only.
            await asyncio.sleep(random.uniform(0, self._reconnect_policy.initial_offset_s))
        while not self._closed:
            session_started_at = time.monotonic()
            try:
                await self._session_loop()
            except asyncio.CancelledError:
                raise
            except LTSNotFoundError:
                # D-07/D-24: LTSNotFoundError is the consumer-facing signal that the
                # event id is invalid (LTS_NOT_FOUND classified as unknown_event).
                # The session_loop stores the exception on self._pending_messages_exc
                # before raising, so the messages() iterator can re-raise it.
                if self._messages_q is not None:
                    await self._messages_q.put(_Sentinel(_SentinelKind.EXHAUSTED))
                return
            except Exception as exc:
                _log.warning("live transport session ended: %s", exc)
            # If the session ran for > 60s, reset the attempt counter (D-11).
            if time.monotonic() - session_started_at > _SUCCESS_RESET_SECONDS:
                attempt = 0
            # Check max_attempts
            if (
                self._reconnect_policy.max_attempts is not None
                and attempt >= self._reconnect_policy.max_attempts
            ):
                _log.error("live transport reconnect exhausted after %d attempts", attempt)
                # Surface the final failure on the messages queue (which the
                # consumer is iterating) and stop the loop.
                if self._messages_q is not None:
                    await self._messages_q.put(_Sentinel(_SentinelKind.EXHAUSTED))
                return
            # Compute next backoff delay (D-10 full jitter).
            delay = random.uniform(
                0.0,
                min(
                    self._reconnect_policy.cap_delay_s,
                    self._reconnect_policy.base_delay_s * (2**attempt),
                ),
            )
            attempt += 1
            _log.info("reconnecting in %.2fs (attempt %d)", delay, attempt)
            await asyncio.sleep(delay)

    async def _session_loop(self) -> None:
        """One connection lifecycle: connect → handshake → frame loop → close."""
        self._state = _ConnectionState(event_id=self._event_id)  # fresh per session

        connect_fn: Callable[..., Awaitable[Any]] = self._websockets_factory  # type: ignore[assignment]
        if connect_fn is None:
            import websockets

            connect_fn = websockets.connect

        url = self._host.rstrip("/") + "/"
        async with await connect_fn(url, **_WS_OPEN_KWARGS) as ws:
            handshake = _dumps(
                {
                    "eventId": self._event_id,
                    "eventPid": list(self._channels),
                    "clientLocalTime": int(time.time() * 1000),
                }
            )
            await ws.send(handshake)
            _log.info("handshake sent for event %s", self._event_id)

            async for raw in ws:
                if self._state is None:
                    return  # close() raced; bail out cleanly
                self._state.record_frame()
                payload = _loads(raw)
                await self._handle_frame(payload)

    async def _handle_frame(self, payload: Any) -> None:
        """Route one frame through :func:`parser.parse` + classifier side-effects.

        The parser is the single entry point for everything except the
        LTS_NOT_FOUND discriminator (which we check first so we never
        enter the typed-Message path for an event we cannot classify).
        Time-sync frames are dispatched by the parser too, but we
        re-check here so we can also update :class:`ClockOffset` and
        enqueue on the dedicated ``time_sync`` queue (D-04).
        """
        if not isinstance(payload, Mapping):
            return  # not an object — skip silently
        # Check LTS_NOT_FOUND before dispatch (D-05).
        if payload.get("LTS_NOT_FOUND"):
            await self._handle_lts_not_found(payload)
            return
        # Dispatch through the parser.
        try:
            msg = parse(payload)
        except Exception as exc:
            _log.warning("parser raised on frame: %s", exc)
            return
        if isinstance(msg, TimeSyncMessage):
            # Update ClockOffset (D-04) and yield on the dedicated iterator.
            local_ms = int(time.time() * 1000)
            self._clock_offset.update(server_time_ms=msg.value_ms, local_recv_ms=local_ms)
            if self._time_sync_q is not None:
                await self._time_sync_q.put(msg)
            return
        # Classifier side-effects (D-06).
        if isinstance(msg, TrackStateMessage):
            assert self._state is not None
            self._state.observe_track_state(
                track_state=getattr(msg, "track_state", None),
                end_time=getattr(msg, "end_time", None),
            )
        elif isinstance(msg, InitialStateMessage):
            assert self._state is not None
            self._state.observe_initial_state(has_results=bool(getattr(msg, "results", ())))
        # Default iterator: messages() (NOT time_sync; D-04).
        if self._messages_q is not None:
            await self._messages_q.put(msg)

    async def _handle_lts_not_found(self, payload: Mapping[str, Any]) -> None:
        """Classify LTS_NOT_FOUND into one of three reasons (D-06) + apply policy (D-07)."""
        assert self._state is not None
        if self._state.first_lts_not_found_at_ms is None:
            self._state.first_lts_not_found_at_ms = int(time.time() * 1000)
        reason = self._classify_lts_not_found()
        event = LTSNotFoundEvent(
            reason=reason,
            event_id=self._event_id,
            first_seen_at_ms=self._state.first_lts_not_found_at_ms,
        )
        _log.info("LTS_NOT_FOUND classified as %r", reason)
        # Apply per-reason policy (D-07).
        action: str = getattr(self._lts_not_found_policy, f"on_{reason}")
        # Yield the event BEFORE raising so consumers can observe the
        # classification regardless of policy.
        if self._lts_q is not None:
            await self._lts_q.put(event)
        if action == "raise":
            # Store the exception so the messages() iterator re-raises it
            # on the next ``async for`` iteration; do not propagate it
            # through the reader loop (which would mask it in the
            # backoff-cycle ``except Exception`` handler).
            self._pending_messages_exc = LTSNotFoundError(
                reason="unknown_event", event_id=self._event_id
            )
            raise self._pending_messages_exc
        if action == "terminate":
            # Stop reconnecting: mark state ended and surface EXHAUSTED sentinel.
            assert self._state is not None
            self._state.ended_seen = True
            if self._messages_q is not None:
                await self._messages_q.put(_Sentinel(_SentinelKind.EXHAUSTED))
            # Cancel the reader task to break out of the reconnect loop.
            if self._reader_task is not None:
                self._reader_task.cancel()

    def _classify_lts_not_found(self) -> LTSNotFoundReason:
        """D-06 heuristic — stateful across the connection lifetime."""
        assert self._state is not None
        if self._state.ended_seen:
            return "ended"
        if (
            self._state.connection_age_seconds() < self._pre_race_threshold_s
            and not self._state.seen_initial_state_with_results
        ):
            return "not_yet_started"
        return "unknown_event"

    async def _idle_watchdog(self) -> None:
        """D-02: force reconnect if no frame received for ``idle_timeout_s``."""
        while not self._closed:
            await asyncio.sleep(min(self._idle_timeout_s / 3.0, 10.0))
            if self._state is None:
                continue
            if self._state.idle_seconds() > self._idle_timeout_s:
                _log.warning(
                    "no frame for %.1fs (limit %.1fs), forcing reconnect",
                    self._state.idle_seconds(),
                    self._idle_timeout_s,
                )
                # Cancel the reader task so the reconnect loop kicks in.
                if self._reader_task is not None:
                    self._reader_task.cancel()
                    return


# Verify Protocol satisfaction at import time — the runtime_checkable
# Protocol would catch a missing method at isinstance() time, but an
# eager check makes mistakes easier to debug.
_ = issubclass(LiveTransport, Transport)
