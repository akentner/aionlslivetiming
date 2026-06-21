"""NLSClient — composition root for aionlslivetiming (Phase 4 D-06..D-12).

Wires ``Transport`` → :class:`~aionlslivetiming.state.RaceState` so a
downstream consumer can write::

    async with NLSClient(event_id=20) as client:
        async for msg in client.messages():
            ...           # state.apply(msg) already ran

or::

    async with NLSClient.from_replay("race.jsonl") as client:
        async for msg in client.messages():
            ...           # same surface; source == REPLAY

Three async iterators are exposed per Phase 3 D-04 + Phase 4 D-10:

- :meth:`messages` — race messages (time-sync excluded).
- :meth:`time_sync` — clock-sync frames, when the transport exposes them
  (LiveTransport always; ReplayTransport only with ``suppress_time_sync=False``).
- :meth:`lts_not_found` — LTS_NOT_FOUND events (LiveTransport only; Replay never).

The state cache is exposed as :attr:`state`. ``source`` reflects the
transport's source (``LIVE``/``REPLAY``/``IMPORTED``). ``clock_offset`` is
a thin delegation to the transport's :class:`ClockOffset`.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from aionlslivetiming.logging import get_logger
from aionlslivetiming.state import RaceState, Source
from aionlslivetiming.transport.base import (
    ClockOffset,
    LTSNotFoundEvent,
    ReconnectPolicy,
    Transport,
)
from aionlslivetiming.transport.recorder import JsonlRecorder
from aionlslivetiming.transport.recorder_wrapper import RecordingTransport
from aionlslivetiming.transport.replay import ReplayTransport
from aionlslivetiming.transport.websocket import LiveTransport, LTSNotFoundPolicy

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
    from pathlib import Path
    from typing import Any

    from aionlslivetiming.events import Message, TimeSyncMessage

_log = get_logger("aionlslivetiming.client")


def _default_channels() -> tuple[int, ...]:
    """Lazy import to avoid a hard import cycle with ``cli/`` at test time."""
    from aionlslivetiming.cli.record import DEFAULT_CHANNELS

    return DEFAULT_CHANNELS


class NLSClient:
    """Composition root: Transport -> State (auto-applied) (D-06..D-12).

    Construct directly for the common live case::

        NLSClient(event_id="20")

    Construct with a power-user-injected transport::

        NLSClient(transport=my_custom_transport)

    Build a replay client via the classmethod::

        NLSClient.from_replay("race.jsonl", speed_factor=2.0)

    Optional ``record_to=path`` wraps a live transport in
    :class:`RecordingTransport` so every yielded message is also persisted
    to a JSONL log.

    Lifecycle is ``async with``::

        async with NLSClient(event_id="20") as client:
            async for msg in client.messages():
                ...

    The state cache is exposed as :attr:`state`. ``state.apply(msg)`` is
    called for every parsed message BEFORE it is yielded by ``messages()``,
    so consumers can read ``client.state.cars`` immediately after the loop
    without further work. Consumers should not call ``state.apply()``
    themselves while the client is iterating.
    """

    def __init__(
        self,
        event_id: str | None = None,
        *,
        host: str = "wss://livetiming.azurewebsites.net/",
        channels: Sequence[int] | None = None,
        transport: Transport | None = None,
        record_to: str | Path | None = None,
        reconnect_policy: ReconnectPolicy | None = None,
        lts_not_found_policy: LTSNotFoundPolicy | None = None,
        state: RaceState | None = None,
        websockets_factory: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        # ---- Transport selection (D-06) ----
        if transport is not None:
            if not isinstance(transport, Transport):
                raise TypeError(
                    f"NLSClient.transport must satisfy Transport "
                    f"(got {type(transport).__name__})"
                )
            self._transport: Transport = transport
        elif event_id is not None:
            inner_live = LiveTransport(
                event_id,
                host=host,
                channels=list(channels) if channels is not None else list(_default_channels()),
                reconnect_policy=reconnect_policy,
                lts_not_found_policy=lts_not_found_policy,
                websockets_factory=websockets_factory,
            )
            if record_to is not None:
                self._transport = RecordingTransport(
                    inner=inner_live, recorder=JsonlRecorder(record_to)
                )
            else:
                self._transport = inner_live
        else:
            raise TypeError("NLSClient requires event_id= or transport=")

        # ---- State ownership (D-08) ----
        if state is not None:
            self._state: RaceState = state
        else:
            self._state = RaceState(source=self._infer_source(self._transport))

    @classmethod
    def from_replay(
        cls,
        path: str | Path,
        *,
        speed_factor: float = 1.0,
        suppress_time_sync: bool = True,
        limit: int | None = None,  # advisory; the CLI in Plan 02 enforces it
        state: RaceState | None = None,
    ) -> NLSClient:
        """Build a replay-mode client wrapping :class:`ReplayTransport` (D-07).

        Construction is lazy: the file is not opened until ``__aenter__``.
        The ``limit`` parameter is reserved for the CLI (Plan 02) which
        enforces a maximum number of parsed messages; the client itself
        iterates to end-of-stream.
        """
        replay = ReplayTransport(
            path, speed_factor=speed_factor, suppress_time_sync=suppress_time_sync
        )
        return cls(transport=replay, state=state)

    # ---- Async context manager ----

    async def __aenter__(self) -> NLSClient:
        await self._transport.connect()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        # Wrap in suppress so cancellation does not propagate out of __aexit__.
        with contextlib.suppress(asyncio.CancelledError):
            await self._transport.close()

    # ---- Async iterators (D-10) ----

    async def messages(self) -> AsyncIterator[Message]:
        """Yield typed Messages; apply each to :attr:`state` BEFORE yielding (D-08)."""
        async for msg in self._transport:
            self._state.apply(msg)
            yield msg

    async def time_sync(self) -> AsyncIterator[TimeSyncMessage]:
        """Delegate to the transport's ``time_sync()`` when present.

        :class:`ReplayTransport` does NOT expose ``time_sync()`` by default
        (Pitfall #10 / Phase 3 D-16: ``suppress_time_sync=True``), so this
        iterator returns immediately in that case.
        """
        ts = getattr(self._transport, "time_sync", None)
        if ts is None:
            return
        async for msg in ts():
            yield msg

    async def lts_not_found(self) -> AsyncIterator[LTSNotFoundEvent]:
        """Delegate to the transport's ``lts_not_found()`` when present.

        Only :class:`LiveTransport` exposes LTS_NOT_FOUND events; replay
        transports never do.
        """
        lts = getattr(self._transport, "lts_not_found", None)
        if lts is None:
            return
        async for ev in lts():
            yield ev

    # ---- Accessors ----

    @property
    def state(self) -> RaceState:
        """The :class:`RaceState` owned by this client (D-08)."""
        return self._state

    @property
    def source(self) -> Source:
        """Origin of the messages fed into this client (D-12)."""
        return self._state.source

    @property
    def clock_offset(self) -> ClockOffset:
        """The transport's :class:`ClockOffset` (D-11).

        All three first-party transports (Live, Replay, Recording) expose
        this; user-supplied transports may not. We use ``getattr`` so the
        property never raises — power-user transports that lack a clock
        offset get a fresh ``ClockOffset`` whose offset is ``None``.
        """
        co = getattr(self._transport, "clock_offset", None)
        if co is None:
            return ClockOffset()
        # First-party transports (Live, Replay, Recording) always expose a
        # ClockOffset at runtime. The Transport Protocol does not declare it
        # (Protocol is the minimum surface), so mypy sees Any — cast.
        from typing import cast

        return cast("ClockOffset", co)

    @property
    def transport(self) -> Transport:
        """The wrapped :class:`Transport` (power-user escape hatch)."""
        return self._transport

    # ---- Repr ----

    def __repr__(self) -> str:
        try:
            ev = getattr(self._transport, "event_id", None)
        except Exception:
            ev = None
        head = f"NLSClient(event_id={ev!r}" if ev is not None else "NLSClient(transport=...)"
        return (
            f"{head}, source={self._state.source.name}, "
            f"state=<RaceState freshness={self._state.freshness.value}>)"
        )

    # ---- Internals ----

    @staticmethod
    def _infer_source(transport: Transport) -> Source:
        """Pick :class:`Source` from the transport's concrete class (D-12)."""
        # Local imports keep top-level import graph clean.
        from aionlslivetiming.transport.recorder_wrapper import RecordingTransport
        from aionlslivetiming.transport.replay import ReplayTransport
        from aionlslivetiming.transport.websocket import LiveTransport

        if isinstance(transport, ReplayTransport):
            return Source.REPLAY
        if isinstance(transport, (LiveTransport, RecordingTransport)):
            # RecordingTransport wrapping a LiveTransport is LIVE (D-08);
            # wrapping a ReplayTransport is degenerate and treated as REPLAY
            # via the ReplayTransport isinstance check above.
            return Source.LIVE
        return Source.LIVE  # safe default for custom transports


__all__ = ["NLSClient"]
