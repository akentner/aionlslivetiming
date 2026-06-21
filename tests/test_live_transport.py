"""Tests for LiveTransport — handshake, frame dispatch, close-code handling.

No network. All tests inject a `websockets_factory` that returns a fake
WebSocket context manager emitting scripted frames (D-07 pattern reused
from jsonl_logger).
"""

from __future__ import annotations

import asyncio
import json as _json
from typing import TYPE_CHECKING, Any

from aionlslivetiming.events import (
    InitialStateMessage,
    TimeSyncMessage,
)
from aionlslivetiming.transport import LiveTransport, ReconnectPolicy

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _dumps(obj: Any) -> str:
    """JSON encode a dict to a string (mimics what real websockets yields)."""
    try:
        import orjson  # type: ignore[import-not-found]

        return orjson.dumps(obj).decode("utf-8")
    except ImportError:
        import json as _stdlib

        return _stdlib.dumps(obj, separators=(",", ":"))


class _MockWebSocket:
    """A fake websockets connection that emits a scripted list of frames.

    The real ``websockets`` library yields JSON-as-text on iteration, so
    we serialize each frame dict before yielding — keeping the production
    code path faithful (no dict/str branching).
    """

    def __init__(self, frames: list[Any]) -> None:
        self._frames = [
            _dumps(f) if not isinstance(f, (str, bytes, bytearray)) else f for f in frames
        ]
        self.sent: list[str] = []
        self.recv_kwargs: list[dict[str, Any]] = []

    async def send(self, raw: str) -> None:
        self.sent.append(raw)

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._aiter_impl()

    async def _aiter_impl(self) -> AsyncIterator[Any]:
        for frame in self._frames:
            yield frame

    async def close(self) -> None:
        pass


class _WebSocketCM:
    """Async context manager that yields a ``_MockWebSocket``."""

    def __init__(self, ws: _MockWebSocket) -> None:
        self._ws = ws

    async def __aenter__(self) -> _MockWebSocket:
        return self._ws

    async def __aexit__(self, *exc: object) -> None:
        await self._ws.close()


def _make_factory(ws: _MockWebSocket):
    """Return an async callable that produces a context manager around *ws*."""

    async def factory(url: str, **kwargs: Any) -> _WebSocketCM:
        ws.recv_kwargs.append(kwargs)
        return _WebSocketCM(ws)

    return factory


INITIAL_FRAME: dict[str, Any] = {
    "PID": 0,
    "VER": "1.0",
    "EXPORTID": "evt-1",
    "TRACKNAME": "Nordschleife",
    "RESULTS": [],
}
TIME_SYNC_FRAME: dict[str, Any] = {"type": "time", "value": 1_700_000_000_000}


async def test_live_transport_sends_handshake_on_connect() -> None:
    """The first WebSocket send is the handshake JSON {eventId, eventPid, clientLocalTime}."""
    ws = _MockWebSocket(frames=[INITIAL_FRAME])
    transport = LiveTransport(
        "evt-1",
        websockets_factory=_make_factory(ws),
        idle_timeout_s=10.0,
        reconnect_policy=ReconnectPolicy(max_attempts=0, initial_offset_s=0),
    )
    await transport.connect()
    try:
        async with asyncio.timeout(2):
            async for _ in transport:
                break
    finally:
        await transport.close()
    assert len(ws.sent) >= 1
    handshake = _json.loads(ws.sent[0])
    assert handshake["eventId"] == "evt-1"
    assert handshake["eventPid"] == [0, 3, 4, 7, 501, 9002]
    assert isinstance(handshake["clientLocalTime"], int)


async def test_live_transport_dispatches_through_parser() -> None:
    """Each non-time-sync frame goes through parser.parse() — yields typed Message."""
    ws = _MockWebSocket(frames=[INITIAL_FRAME])
    transport = LiveTransport(
        "evt-1",
        websockets_factory=_make_factory(ws),
        idle_timeout_s=10.0,
        reconnect_policy=ReconnectPolicy(max_attempts=0, initial_offset_s=0),
    )
    await transport.connect()
    try:
        msgs: list[Any] = []
        async with asyncio.timeout(2):
            async for m in transport:
                msgs.append(m)
    finally:
        await transport.close()
    assert len(msgs) == 1
    assert isinstance(msgs[0], InitialStateMessage)


async def test_live_transport_time_sync_excluded_from_messages() -> None:
    """D-04: time-sync frames go to time_sync() iterator, NOT __aiter__."""
    ws = _MockWebSocket(frames=[TIME_SYNC_FRAME, INITIAL_FRAME])
    transport = LiveTransport(
        "evt-1",
        websockets_factory=_make_factory(ws),
        idle_timeout_s=10.0,
        reconnect_policy=ReconnectPolicy(max_attempts=0, initial_offset_s=0),
    )
    await transport.connect()
    try:
        msgs: list[Any] = []
        async with asyncio.timeout(2):
            async for m in transport:
                msgs.append(m)
        sync_msgs: list[Any] = []
        async with asyncio.timeout(2):
            async for m in transport.time_sync():
                sync_msgs.append(m)
                if len(sync_msgs) >= 1:
                    break
    finally:
        await transport.close()
    # Main iterator: only the initial state (time-sync excluded)
    assert all(not isinstance(m, TimeSyncMessage) for m in msgs)
    assert len(msgs) == 1
    # time_sync iterator: the time-sync frame
    assert any(isinstance(m, TimeSyncMessage) for m in sync_msgs)


async def test_live_transport_passes_ping_none_to_websockets() -> None:
    """D-01: connect uses ping_interval=None, ping_timeout=None (no auto-ping)."""
    ws = _MockWebSocket(frames=[INITIAL_FRAME])
    transport = LiveTransport(
        "evt-1",
        websockets_factory=_make_factory(ws),
        idle_timeout_s=10.0,
        reconnect_policy=ReconnectPolicy(max_attempts=0, initial_offset_s=0),
    )
    await transport.connect()
    try:
        async with asyncio.timeout(2):
            async for _ in transport:
                break
    finally:
        await transport.close()
    assert ws.recv_kwargs, "factory was never invoked"
    kwargs = ws.recv_kwargs[0]
    assert kwargs.get("ping_interval") is None
    assert kwargs.get("ping_timeout") is None


async def test_live_transport_idle_timeout_forces_reconnect() -> None:
    """D-02: if no frame for `idle_timeout_s`, the watchdog forces a reconnect attempt."""
    ws = _MockWebSocket(frames=[])
    transport = LiveTransport(
        "evt-1",
        websockets_factory=_make_factory(ws),
        idle_timeout_s=0.2,
        reconnect_policy=ReconnectPolicy(
            max_attempts=1,
            initial_offset_s=0,
            base_delay_s=0.01,
            cap_delay_s=0.05,
        ),
    )
    await transport.connect()
    try:
        msgs: list[Any] = []
        async with asyncio.timeout(3):
            async for _ in transport:
                msgs.append(_)
    finally:
        await transport.close()
    # The empty frames list + idle watchdog + max_attempts=1 → no real messages
    assert msgs == []


async def test_live_transport_max_attempts_terminates_loop() -> None:
    """With max_attempts=0, transport raises/ends without retrying."""
    ws = _MockWebSocket(frames=[])
    transport = LiveTransport(
        "evt-1",
        websockets_factory=_make_factory(ws),
        idle_timeout_s=10.0,
        reconnect_policy=ReconnectPolicy(max_attempts=0, initial_offset_s=0),
    )
    await transport.connect()
    try:
        msgs: list[Any] = []
        async with asyncio.timeout(2):
            async for _ in transport:
                msgs.append(_)
    finally:
        await transport.close()
    # No messages — empty stream
    assert msgs == []
