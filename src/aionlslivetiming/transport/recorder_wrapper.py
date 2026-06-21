"""RecordingTransport — composes any inner Transport with a JsonlRecorder.

Wraps a :class:`Transport` instance and a :class:`JsonlRecorder` instance.
Every Message yielded by the inner transport is also appended to the
recorder BEFORE being yielded by the wrapper, so a downstream consumer's
RaceState (Phase 4) is never ahead of the on-disk log (Pitfall #11).

This is composition, NOT subclassing — RecordingTransport can wrap
LiveTransport, ReplayTransport, or even another RecordingTransport
(though the latter is degenerate).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aionlslivetiming.logging import get_logger
from aionlslivetiming.transport.base import Transport

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from aionlslivetiming.events import Message
    from aionlslivetiming.transport.recorder import JsonlRecorder


_log = get_logger("aionlslivetiming.transport.recorder_wrapper")


class RecordingTransport:
    """Composition wrapper that tees every Message to a JsonlRecorder.

    Usage::

        rec = JsonlRecorder(path)
        inner = LiveTransport(event_id)
        transport = RecordingTransport(inner=inner, recorder=rec)
        await transport.connect()
        async for msg in transport:   # also written to `rec`
            ...
        await transport.close()        # flushes the recorder

    Or as an async context manager::

        async with JsonlRecorder(path) as rec:
            transport = RecordingTransport(inner=inner, recorder=rec)
            async with transport:
                async for msg in transport:
                    ...
            # recorder is flushed on context exit
    """

    def __init__(self, inner: Transport, recorder: JsonlRecorder) -> None:
        if not isinstance(inner, Transport):
            raise TypeError(
                f"RecordingTransport.inner must satisfy Transport (got {type(inner).__name__})"
            )
        self._inner = inner
        self._recorder = recorder

    @property
    def inner(self) -> Transport:
        """The wrapped transport (for inspection / clock_offset access)."""
        return self._inner

    @property
    def recorder(self) -> JsonlRecorder:
        """The recorder (for inspection / flushing)."""
        return self._recorder

    @property
    def is_enabled(self) -> bool:
        """Whether the wrapped recorder is currently persisting (REC-02)."""
        return self._recorder.is_enabled

    async def set_enabled(self, enabled: bool) -> None:
        """Toggle the wrapped recorder at runtime (REC-02 passthrough).

        Forwards to the inner ``JsonlRecorder.set_enabled``. While disabled,
        ``__aiter__`` still forwards every message from the inner transport
        to the consumer — only the on-disk recording pauses.
        """
        await self._recorder.set_enabled(enabled)

    async def __aenter__(self) -> RecordingTransport:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def connect(self) -> None:
        """Open the inner transport (does NOT open the recorder — that's lazy)."""
        await self._inner.connect()

    async def close(self) -> None:
        """Close the inner transport AND flush the recorder.

        Idempotent. Order matters: close the inner transport first so no
        more messages flow into the recorder, then close the recorder.
        """
        await self._inner.close()
        await self._recorder.close()

    async def __aiter__(self) -> AsyncIterator[Message]:
        """Yield each message from the inner transport AFTER persisting it.

        The append-then-yield ordering is the load-bearing invariant:
        a consumer iterating the messages stream sees a message only
        after it has been written to the recorder. This means the
        on-disk log is always at least as fresh as any downstream state.
        """
        async for msg in self._inner:
            await self._recorder.append(msg)
            yield msg


__all__ = ["RecordingTransport"]
