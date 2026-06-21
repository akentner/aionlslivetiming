"""Tests for LTS_NOT_FOUND three-state classification (D-05..D-08).

Exercises the classifier through LiveTransport end-to-end with a mock
WebSocket (D-07 injection pattern). The classifier is implemented in
``LiveTransport._classify_lts_not_found``; this file covers the
behavioural contract.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

from aionlslivetiming.events import TrackStateMessage
from aionlslivetiming.exceptions import UnknownEventError
from aionlslivetiming.transport import (
    LiveTransport,
    LTSNotFoundEvent,
    LTSNotFoundPolicy,
    ReconnectPolicy,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    pass


# ---- Mock WebSocket (mirror of test_live_transport.py — kept local
# to keep each test file self-contained) ----


def _dumps(obj: Any) -> str:
    """JSON encode a dict to a string (mimics what real websockets yields)."""
    try:
        import orjson

        return orjson.dumps(obj).decode("utf-8")
    except ImportError:
        import json as _stdlib

        return _stdlib.dumps(obj, separators=(",", ":"))


class _MockWS:
    """A fake websockets connection that emits a scripted list of frames."""

    def __init__(self, frames: list[Any]) -> None:
        self._frames = [
            _dumps(f) if not isinstance(f, (str, bytes, bytearray)) else f for f in frames
        ]
        self.sent: list[str] = []

    async def send(self, raw: str) -> None:
        self.sent.append(raw)

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._aiter_impl()

    async def _aiter_impl(self) -> AsyncIterator[Any]:
        for f in self._frames:
            yield f

    async def close(self) -> None:
        pass


class _CM:
    """Async context manager that yields a ``_MockWS``."""

    def __init__(self, ws: _MockWS) -> None:
        self._ws = ws

    async def __aenter__(self) -> _MockWS:
        return self._ws

    async def __aexit__(self, *exc: object) -> None:
        await self._ws.close()


def _factory_for(ws: _MockWS):
    """Return an async callable that produces a context manager around *ws*."""

    async def factory(url: str, **kw: Any) -> _CM:
        return _CM(ws)

    return factory


# ---- Frame fixtures ----

LTS_FRAME: dict[str, Any] = {"LTS_NOT_FOUND": True, "eventPid": 0}
INIT_WITH_RESULTS: dict[str, Any] = {
    "eventPid": 0,
    "PID": 0,
    "VER": "1.0",
    "EXPORTID": "e",
    "TRACKNAME": "Nordschleife",
    "SESSION": "R1",
    "RESULT": [{"startingNo": 1, "position": 1, "class": "SP9", "driver": "M"}],
}
TRACK_FINISHED: dict[str, Any] = {
    "eventPid": 4,
    "PID": 4,
    "VER": "1.0",
    "TRACKSTATE": "FINISHED",
    "TOD": {"value": 12 * 3600 * 1000},
    "ENDTIME": {"value": (12 * 3600 + 30 * 60) * 1000},
}
TRACK_GREEN: dict[str, Any] = {
    "eventPid": 4,
    "PID": 4,
    "VER": "1.0",
    "TRACKSTATE": "GREEN",
    "TOD": {"value": 12 * 3600 * 1000},
}


# ---- Classifier behaviour ----


async def test_lts_not_found_unknown_event_default_raises() -> None:
    """D-07 default: unknown_event → raise UnknownEventError."""
    # Frame flow: an InitialStateMessage with results (so we don't classify
    # as not_yet_started), then LTS_NOT_FOUND.
    ws = _MockWS(frames=[INIT_WITH_RESULTS, LTS_FRAME])
    transport = LiveTransport(
        "evt-1",
        websockets_factory=_factory_for(ws),
        idle_timeout_s=10.0,
        reconnect_policy=ReconnectPolicy(max_attempts=0, initial_offset_s=0),
    )
    await transport.connect()
    try:
        with pytest.raises(UnknownEventError):
            async with asyncio.timeout(2):
                async for _ in transport:
                    pass
    finally:
        await transport.close()


async def test_lts_not_found_yields_typed_event_before_raise() -> None:
    """When policy is raise, the event still gets yielded to lts_not_found() first."""
    ws = _MockWS(frames=[INIT_WITH_RESULTS, LTS_FRAME])
    transport = LiveTransport(
        "evt-1",
        websockets_factory=_factory_for(ws),
        idle_timeout_s=10.0,
        reconnect_policy=ReconnectPolicy(max_attempts=0, initial_offset_s=0),
    )
    await transport.connect()
    raised = False
    try:
        try:
            async with asyncio.timeout(2):
                async for _ in transport:
                    pass
        except UnknownEventError:
            raised = True
        # Drain lts_not_found queue — the event was enqueued before the raise.
        events: list[LTSNotFoundEvent] = []
        async with asyncio.timeout(1):
            async for ev in transport.lts_not_found():
                events.append(ev)
                if len(events) >= 1:
                    break
    finally:
        await transport.close()
    assert raised
    assert len(events) == 1
    assert events[0].reason == "unknown_event"
    assert events[0].event_id == "evt-1"


async def test_lts_not_found_ended_after_trackstate_finished() -> None:
    """D-06: a TrackStateMessage with TRACKSTATE=FINISHED → next LTS_NOT_FOUND = `ended`."""
    ws = _MockWS(frames=[TRACK_FINISHED, LTS_FRAME])
    transport = LiveTransport(
        "evt-1",
        websockets_factory=_factory_for(ws),
        idle_timeout_s=10.0,
        reconnect_policy=ReconnectPolicy(max_attempts=0, initial_offset_s=0),
        lts_not_found_policy=LTSNotFoundPolicy(on_ended="terminate"),
    )
    await transport.connect()
    msgs: list[Any] = []
    events: list[LTSNotFoundEvent] = []
    try:
        async with asyncio.timeout(2):
            async for m in transport:
                msgs.append(m)
        async with asyncio.timeout(1):
            async for ev in transport.lts_not_found():
                events.append(ev)
                if len(events) >= 1:
                    break
    finally:
        await transport.close()
    # TrackStateMessage flowed through
    assert any(isinstance(m, TrackStateMessage) for m in msgs)
    # The LTS event was classified as `ended`
    assert any(ev.reason == "ended" for ev in events)
    # transport.ended reflects the state
    assert transport.ended is True


async def test_lts_not_found_not_yet_started_silently_reconnects() -> None:
    """D-06 + D-07: young connection + no initial state → not_yet_started → continue."""
    ws = _MockWS(frames=[LTS_FRAME])
    transport = LiveTransport(
        "evt-1",
        websockets_factory=_factory_for(ws),
        idle_timeout_s=10.0,
        pre_race_threshold_s=300.0,  # default — connection age is ~0s
        reconnect_policy=ReconnectPolicy(
            max_attempts=1,
            initial_offset_s=0,
            base_delay_s=0.01,
            cap_delay_s=0.05,
        ),
    )
    await transport.connect()
    msgs: list[Any] = []
    events: list[LTSNotFoundEvent] = []
    try:
        async with asyncio.timeout(3):
            async for m in transport:
                msgs.append(m)
        async with asyncio.timeout(1):
            async for ev in transport.lts_not_found():
                events.append(ev)
                if len(events) >= 1:
                    break
    finally:
        await transport.close()
    # The event was classified as not_yet_started
    assert any(ev.reason == "not_yet_started" for ev in events)
    # transport.ended is False (not_yet_started is non-terminal)
    assert transport.ended is False


async def test_lts_not_found_policy_continue_on_ended() -> None:
    """D-08 override: on_ended='continue' → keep retrying instead of terminating."""
    ws = _MockWS(frames=[TRACK_FINISHED, LTS_FRAME])
    transport = LiveTransport(
        "evt-1",
        websockets_factory=_factory_for(ws),
        idle_timeout_s=10.0,
        reconnect_policy=ReconnectPolicy(
            max_attempts=1,
            initial_offset_s=0,
            base_delay_s=0.01,
            cap_delay_s=0.05,
        ),
        lts_not_found_policy=LTSNotFoundPolicy(on_ended="continue"),
    )
    await transport.connect()
    events: list[LTSNotFoundEvent] = []
    try:
        async with asyncio.timeout(3):
            async for _ in transport:
                pass
        async with asyncio.timeout(1):
            async for ev in transport.lts_not_found():
                events.append(ev)
                if len(events) >= 1:
                    break
    finally:
        await transport.close()
    # Event was classified as ended but policy was continue
    assert any(ev.reason == "ended" for ev in events)


# ---- LTSNotFoundPolicy validation ----


def test_lts_not_found_policy_invalid_value_raises() -> None:
    """Constructing LTSNotFoundPolicy with an invalid value raises ValueError."""
    with pytest.raises(ValueError):
        LTSNotFoundPolicy(on_ended="bogus")  # type: ignore[arg-type]


def test_lts_not_found_policy_defaults() -> None:
    """LTSNotFoundPolicy defaults match D-07."""
    p = LTSNotFoundPolicy()
    assert p.on_not_yet_started == "continue"
    assert p.on_ended == "terminate"
    assert p.on_unknown_event == "raise"


def test_lts_not_found_policy_repr() -> None:
    """LTSNotFoundPolicy has a readable repr (no surprises in logs)."""
    p = LTSNotFoundPolicy()
    r = repr(p)
    assert "on_not_yet_started" in r
    assert "on_ended" in r
    assert "on_unknown_event" in r


# ---- LTSNotFoundEvent immutability ----


def test_lts_not_found_event_is_frozen() -> None:
    """LTSNotFoundEvent is frozen; mutation raises."""
    import dataclasses

    ev = LTSNotFoundEvent(reason="unknown_event", event_id="x", first_seen_at_ms=1000)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.reason = "ended"  # type: ignore[misc]


def test_lts_not_found_event_fields_accessible() -> None:
    """LTSNotFoundEvent exposes reason, event_id, first_seen_at_ms."""
    ev = LTSNotFoundEvent(reason="ended", event_id="abc", first_seen_at_ms=1_700_000_000_000)
    assert ev.reason == "ended"
    assert ev.event_id == "abc"
    assert ev.first_seen_at_ms == 1_700_000_000_000
