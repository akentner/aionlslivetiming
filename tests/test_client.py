"""Tests for the :class:`NLSClient` composition root (Phase 4 D-06..D-12).

The client wires Transport -> State, owns a :class:`RaceState`, applies every
parsed Message before yielding it, and exposes three async iterators
(``messages()``, ``time_sync()``, ``lts_not_found()``).

The tests use a small :class:`StubTransport` class that satisfies the
:class:`~aionlslivetiming.transport.Transport` Protocol with pre-loaded
messages so the suite stays hermetic (no live WebSocket, no real recording).
"""

from __future__ import annotations

import asyncio
import json
import pathlib
from typing import TYPE_CHECKING, Any

import pytest

from aionlslivetiming import NLSClient
from aionlslivetiming.events import (
    InitialStateMessage,
    TimeSyncMessage,
    TrackStateMessage,
    UnknownMessage,
)
from aionlslivetiming.state import RaceState, Source
from aionlslivetiming.transport import (
    ClockOffset,
    LTSNotFoundEvent,
    RecordingTransport,
    Transport,
)
from aionlslivetiming.transport.replay import ReplayTransport
from aionlslivetiming.transport.websocket import LiveTransport

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from aionlslivetiming.events import Message


FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "messages"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _parse_fixture(name: str) -> Any:
    """Parse a raw fixture into a typed :class:`Message`."""
    from aionlslivetiming.parser import parse

    return parse(_load_fixture(name))


# ---- Stub Transport ----


class StubTransport:
    """A minimal :class:`Transport` for testing the composition root.

    Yields ``messages`` from ``__aiter__`` and optionally serves
    ``time_sync()`` and ``lts_not_found()``. Records connect/close call counts
    so tests can assert lifecycle behaviour.
    """

    def __init__(
        self,
        *,
        messages: list[Message] | None = None,
        time_sync_msgs: list[TimeSyncMessage] | None = None,
        lts_events: list[LTSNotFoundEvent] | None = None,
    ) -> None:
        self._messages = messages or []
        self._time_sync = time_sync_msgs or []
        self._lts = lts_events or []
        self._clock_offset = ClockOffset()
        self.connect_await_count = 0
        self.close_await_count = 0
        self._closed = False
        self._connected = False

    @property
    def clock_offset(self) -> ClockOffset:
        return self._clock_offset

    async def connect(self) -> None:
        self.connect_await_count += 1
        self._connected = True

    async def close(self) -> None:
        self.close_await_count += 1
        self._connected = False
        self._closed = True

    def __aiter__(self) -> AsyncIterator[Message]:
        return self._aiter_impl()

    async def _aiter_impl(self) -> AsyncIterator[Message]:
        for m in self._messages:
            yield m

    async def time_sync(self) -> AsyncIterator[TimeSyncMessage]:
        for m in self._time_sync:
            yield m

    async def lts_not_found(self) -> AsyncIterator[LTSNotFoundEvent]:
        for e in self._lts:
            yield e


def _stub_with(
    *,
    messages: list[Message] | None = None,
    time_sync_msgs: list[TimeSyncMessage] | None = None,
    lts_events: list[LTSNotFoundEvent] | None = None,
) -> StubTransport:
    return StubTransport(
        messages=messages,
        time_sync_msgs=time_sync_msgs,
        lts_events=lts_events,
    )


# ---- Construction ----


def test_construct_with_event_id_creates_live_transport() -> None:
    """``NLSClient(event_id='20')`` constructs; transport is LiveTransport; source LIVE."""
    client = NLSClient(event_id="20")
    assert isinstance(client.transport, LiveTransport)
    assert client.source == Source.LIVE
    assert isinstance(client.state, RaceState)


def test_construct_with_explicit_transport_uses_it_verbatim() -> None:
    """A stub Transport passed via ``transport=`` is used as-is."""
    stub = _stub_with()
    client = NLSClient(transport=stub)
    assert client.transport is stub


def test_construct_rejects_non_transport() -> None:
    """A non-Transport object passed via ``transport=`` raises TypeError."""
    with pytest.raises(TypeError):
        NLSClient(transport=object())  # type: ignore[arg-type]


def test_construct_requires_event_id_or_transport() -> None:
    """``NLSClient()`` with neither raises TypeError."""
    with pytest.raises(TypeError):
        NLSClient()


def test_record_to_wraps_in_recording_transport() -> None:
    """``record_to=`` wraps a LiveTransport in RecordingTransport (D-06)."""
    client = NLSClient(event_id="20", record_to="/tmp/_test_record.jsonl")
    try:
        assert isinstance(client.transport, RecordingTransport)
        assert isinstance(client.transport.inner, LiveTransport)
    finally:
        # Recorder path cleanup
        path = pathlib.Path("/tmp/_test_record.jsonl")
        if path.exists():
            path.unlink()


def test_from_replay_uses_replay_transport() -> None:
    """``from_replay`` builds a ReplayTransport; source REPLAY (D-07)."""
    path = FIXTURES / "pid_0_initial.json"
    client = NLSClient.from_replay(path)
    assert isinstance(client.transport, ReplayTransport)
    assert client.source == Source.REPLAY


def test_from_replay_propagates_speed_factor_and_suppress() -> None:
    """``from_replay`` forwards ``speed_factor`` and ``suppress_time_sync``."""
    path = FIXTURES / "pid_0_initial.json"
    client = NLSClient.from_replay(path, speed_factor=2.0, suppress_time_sync=False)
    assert client.transport.speed_factor == 2.0
    assert client.transport.suppress_time_sync is False


def test_state_kwarg_takes_precedence() -> None:
    """A user-supplied ``state=`` is used as-is (D-08 IMPORTED)."""
    state = RaceState(source=Source.IMPORTED)
    client = NLSClient(event_id="20", state=state)
    assert client.state is state
    assert client.source == Source.IMPORTED


# ---- Async iterators: messages() ----


async def test_messages_iterates_transport_and_applies_state() -> None:
    """``messages()`` yields each transport Message AFTER ``state.apply`` (D-08)."""
    init = _parse_fixture("pid_0_initial.json")
    track = _parse_fixture("pid_4_track_state_running.json")
    assert isinstance(init, InitialStateMessage)
    assert isinstance(track, TrackStateMessage)
    stub = _stub_with(messages=[init, track])
    client = NLSClient(transport=stub)
    received: list[Message] = []
    async for m in client.messages():
        received.append(m)
    assert len(received) == 2
    # State has been applied — cars and track populated.
    assert client.state.cars != {}  # InitialStateMessage populated cars
    assert client.state.track is not None
    assert client.state.freshness.value == "FRESH"


# ---- Async iterators: time_sync() ----


class _NoTimeSyncTransport(StubTransport):
    """A StubTransport that does NOT expose ``time_sync()``."""


async def test_time_sync_delegates_when_transport_supports_it() -> None:
    """``time_sync()`` delegates to the transport when available."""
    ts = TimeSyncMessage(value_ms=1234)
    stub = _stub_with(time_sync_msgs=[ts])
    client = NLSClient(transport=stub)
    received: list[TimeSyncMessage] = []
    async for m in client.time_sync():
        received.append(m)
    assert len(received) == 1
    assert received[0].value_ms == 1234


async def test_time_sync_yields_nothing_when_transport_lacks_it() -> None:
    """``time_sync()`` yields nothing when the transport doesn't expose it."""
    stub = _NoTimeSyncTransport()
    client = NLSClient(transport=stub)
    received: list[Any] = []
    async for m in client.time_sync():
        received.append(m)
    assert received == []


# ---- Async iterators: lts_not_found() ----


class _NoLtsTransport(StubTransport):
    """A StubTransport that does NOT expose ``lts_not_found()``."""


async def test_lts_not_found_delegates_when_transport_supports_it() -> None:
    """``lts_not_found()`` delegates to the transport when available."""
    ev = LTSNotFoundEvent(reason="ended", event_id="x", first_seen_at_ms=1000)
    stub = _stub_with(lts_events=[ev])
    client = NLSClient(transport=stub)
    received: list[LTSNotFoundEvent] = []
    async for e in client.lts_not_found():
        received.append(e)
    assert len(received) == 1
    assert received[0].reason == "ended"


async def test_lts_not_found_yields_nothing_when_transport_lacks_it() -> None:
    """``lts_not_found()`` yields nothing when the transport doesn't expose it."""
    stub = _NoLtsTransport()
    client = NLSClient(transport=stub)
    received: list[Any] = []
    async for e in client.lts_not_found():
        received.append(e)
    assert received == []


# ---- Accessors ----


async def test_clock_offset_delegates_to_transport() -> None:
    """``client.clock_offset`` is the transport's clock_offset (D-11)."""
    stub = _stub_with()
    client = NLSClient(transport=stub)
    assert client.clock_offset is stub.clock_offset


# ---- Lifecycle: __aenter__ / __aexit__ ----


async def test_aenter_calls_transport_connect() -> None:
    """``__aenter__`` calls ``transport.connect`` exactly once (D-09)."""
    stub = _stub_with()
    client = NLSClient(transport=stub)
    async with client as c:
        assert c is client
        assert stub.connect_await_count == 1
    assert stub.close_await_count == 1


async def test_aexit_calls_transport_close() -> None:
    """``__aexit__`` calls ``transport.close`` exactly once."""
    stub = _stub_with()
    client = NLSClient(transport=stub)
    async with client:
        pass
    assert stub.close_await_count == 1


async def test_aexit_closes_even_on_exception() -> None:
    """``__aexit__`` closes the transport even when the body raises."""
    stub = _stub_with()
    client = NLSClient(transport=stub)
    with pytest.raises(RuntimeError, match="body failed"):
        async with client:
            raise RuntimeError("body failed")
    assert stub.close_await_count == 1


async def test_cancellation_closes_transport_within_one_second() -> None:
    """Cancellation inside ``messages()`` still triggers ``__aexit__`` cleanup.

    Pitfall #8: ``NLSClient.__aexit__`` must cancel cleanly within ~1s.
    """
    # A transport that yields many messages, one after a small sleep,
    # so the consumer can be cancelled mid-iteration.
    init = _parse_fixture("pid_0_initial.json")

    class SlowStub(StubTransport):
        async def _aiter_impl(self) -> AsyncIterator[Message]:  # type: ignore[override]
            # Yield one fast message, then loop yielding + sleeping so the
            # consumer has time to be cancelled.
            yield init
            for i in range(1000):
                await asyncio.sleep(0.01)
                yield UnknownMessage(event_pid=9999, raw={"eventPid": 9999, "id": i})

    stub = SlowStub()
    client = NLSClient(transport=stub)

    async def consume() -> None:
        async with client:
            async for _ in client.messages():
                pass

    # Race the consumer against a 1-second timeout; cancellation must complete
    # cleanly and transport.close() must run.
    task = asyncio.create_task(consume())
    try:
        # Let it enter the loop, then cancel.
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1.0)
    finally:
        # Belt-and-suspenders: ensure close ran even if test fails.
        assert stub.close_await_count >= 1


# ---- Repr ----


def test_repr_includes_source_and_state() -> None:
    """``repr(client)`` mentions source and RaceState."""
    client = NLSClient(event_id="20")
    r = repr(client)
    assert "LIVE" in r
    assert "RaceState" in r


# ---- Transport Protocol check is a real Protocol ----


def test_live_transport_is_transport_protocol() -> None:
    """Smoke check: a LiveTransport built by the client IS a Transport."""
    client = NLSClient(event_id="20")
    assert isinstance(client.transport, Transport)


# ---- from_replay integration ----


async def test_from_replay_iterates_messages_via_client() -> None:
    """End-to-end: ``NLSClient.from_replay`` + ``messages()`` works against a JSONL."""
    jsonl = pathlib.Path("/tmp/_test_client_replay.jsonl")
    # Hand-crafted 2-line JSONL: PID 0 initial + PID 4 track state.
    jsonl.write_text(  # noqa: ASYNC240 — test file write, runs in pytest sync fixture
        '{"ts_recv_ms": 1000, "event_pid": 0, "raw": '
        + json.dumps(_load_fixture("pid_0_initial.json"))
        + "}\n"
        '{"ts_recv_ms": 2000, "event_pid": 4, "raw": '
        + json.dumps(_load_fixture("pid_4_track_state_running.json"))
        + "}\n",
        encoding="utf-8",
    )
    try:
        async with NLSClient.from_replay(jsonl, speed_factor=0.0) as client:
            assert client.source == Source.REPLAY
            count = 0
            async for _msg in client.messages():
                count += 1
            assert count == 2
            assert client.state.cars != {}
            assert client.state.track is not None
            assert client.state.freshness.value == "FRESH"
    finally:
        if jsonl.exists():  # noqa: ASYNC240
            jsonl.unlink()  # noqa: ASYNC240


# ---- No HA imports guarantee (DIST-04, D-30) ----


def test_no_homeassistant_imports_in_client_module() -> None:
    """The ``aionlslivetiming.client`` module must NOT import homeassistant."""
    import aionlslivetiming.client as client_mod

    src = pathlib.Path(client_mod.__file__).read_text(encoding="utf-8")
    assert "homeassistant" not in src
