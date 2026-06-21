"""Tests for RecordingTransport — composition wrapper around any Transport.

These tests cover the load-bearing invariants of the composition wrapper:
- It tees every yielded Message to the wrapped JsonlRecorder BEFORE yielding it
  (Pitfall #11: recorder is never behind the iterator).
- It satisfies the Transport Protocol (composition is symmetric).
- It composes with ReplayTransport AND LiveTransport (any inner Transport works).
- close() flushes the recorder (idempotent).
- Passing a non-Transport inner raises TypeError.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from aionlslivetiming.events import InitialStateMessage
from aionlslivetiming.transport import (
    JsonlRecorder,
    LiveTransport,
    ReconnectPolicy,
    RecordingTransport,
    ReplayTransport,
    Transport,
)

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator, Awaitable, Callable


# ---------- helpers ----------


def write_d07_jsonl(path: pathlib.Path) -> None:
    """Write a 3-line JSONL that exercises 3 PIDs (initial-state, track-state, race-message).

    Real server payloads carry BOTH `eventPid` (multiplex channel id, what the
    parser dispatches on) AND `PID` (short-code payload key). Including both
    keeps the fixtures honest with the production code path.
    """
    lines = [
        {
            "ts_recv_ms": 1000,
            "raw": {
                "eventPid": 0,
                "PID": 0,
                "VER": "1.0",
                "EXPORTID": "e",
                "TRACKNAME": "Nordschleife",
                "RESULTS": [],
            },
        },
        {"ts_recv_ms": 2000, "raw": {"eventPid": 4, "PID": 4, "VER": "1.0", "TRACKSTATE": "GREEN"}},
        {
            "ts_recv_ms": 3000,
            "raw": {
                "eventPid": 3,
                "PID": 3,
                "VER": "1.0",
                "TEXT": "Pit stop",
                "CATEGORY": "INFO",
                "SESSION": "R1",
            },
        },
    ]
    with path.open("w", encoding="utf-8") as fh:
        for ln in lines:
            fh.write(json.dumps(ln) + "\n")


def _read_text(p: pathlib.Path) -> str:
    """Sync helper used with asyncio.to_thread to silence ruff ASYNC240."""
    return p.read_text(encoding="utf-8")


def _exists(p: pathlib.Path) -> bool:
    return p.exists()


# ---------- composition around ReplayTransport ----------


async def test_recording_transport_wraps_replay(tmp_path: pathlib.Path) -> None:
    """RecordingTransport(ReplayTransport, JsonlRecorder) yields + records."""
    src = tmp_path / "src.jsonl"
    dst = tmp_path / "dst.jsonl"
    write_d07_jsonl(src)

    rec = JsonlRecorder(dst)
    inner = ReplayTransport(src, suppress_time_sync=True)
    rt = RecordingTransport(inner=inner, recorder=rec)

    msgs = [m async for m in rt]
    await rt.close()

    # All 3 source messages yielded
    assert len(msgs) == 3
    # Recorded file has all 3 messages
    content = await asyncio.to_thread(_read_text, dst)
    lines = content.strip().split("\n")
    assert len(lines) == 3
    for line in lines:
        obj = json.loads(line)
        # Phase 3 superset schema: ts_recv_ms, event_pid, raw, parsed
        assert "event_pid" in obj
        assert "raw" in obj
        assert obj["event_pid"] in (0, 4, 3)


async def test_recording_transport_yields_after_recording(tmp_path: pathlib.Path) -> None:
    """Invariant (Pitfall #11): every yielded message has been persisted."""
    src = tmp_path / "src.jsonl"
    dst = tmp_path / "dst.jsonl"
    write_d07_jsonl(src)

    rec = JsonlRecorder(dst)
    inner = ReplayTransport(src, suppress_time_sync=True)
    rt = RecordingTransport(inner=inner, recorder=rec)

    yielded = 0
    async for _m in rt:
        yielded += 1
        # Yield control so the recorder's writer task can drain the queue.
        await asyncio.sleep(0)
        if await asyncio.to_thread(_exists, dst):
            content = await asyncio.to_thread(_read_text, dst)
            recorded = len(content.strip().split("\n")) if content.strip() else 0
        else:
            recorded = 0
        assert recorded >= yielded, (
            f"recorder behind iterator: yielded={yielded}, recorded={recorded}"
        )
    assert yielded == 3
    await rt.close()


async def test_recording_transport_satisfies_transport_protocol(tmp_path: pathlib.Path) -> None:
    """RecordingTransport is itself a Transport (composition is symmetric)."""
    src = tmp_path / "src.jsonl"
    write_d07_jsonl(src)
    rec = JsonlRecorder(src.with_name("out.jsonl"))
    rt = RecordingTransport(inner=ReplayTransport(src), recorder=rec)
    assert isinstance(rt, Transport)


async def test_recording_transport_rejects_non_transport_inner(tmp_path: pathlib.Path) -> None:
    """Passing a non-Transport to RecordingTransport raises TypeError."""
    with pytest.raises(TypeError):
        # Intentional: the constructor must reject anything that is not a
        # Transport (this is the test). Mypy would otherwise complain about
        # the incompatible type — that's the point.
        RecordingTransport(inner="not a transport", recorder=JsonlRecorder(tmp_path / "x.jsonl"))  # type: ignore[arg-type]


async def test_recording_transport_close_flushes_recorder(tmp_path: pathlib.Path) -> None:
    """close() closes the inner transport AND flushes the recorder."""
    src = tmp_path / "src.jsonl"
    dst = tmp_path / "dst.jsonl"
    write_d07_jsonl(src)

    rec = JsonlRecorder(dst)
    rt = RecordingTransport(inner=ReplayTransport(src), recorder=rec)
    async for _ in rt:
        pass
    await rt.close()

    assert await asyncio.to_thread(_exists, dst)
    content = await asyncio.to_thread(_read_text, dst)
    assert len(content.strip().split("\n")) == 3


# ---------- composition around LiveTransport ----------


def _dumps(obj: Any) -> str:
    """JSON encode a dict to a string (mimics what real websockets yields)."""
    try:
        import orjson

        return orjson.dumps(obj).decode("utf-8")
    except ImportError:
        import json as _stdlib

        return _stdlib.dumps(obj, separators=(",", ":"))


class _MockWS:
    """Minimal scripted-frames mock — mirrors test_live_transport._MockWebSocket."""

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
        for f in self._frames:
            yield f

    async def close(self) -> None:
        pass


class _CM:
    def __init__(self, ws: _MockWS) -> None:
        self._ws = ws

    async def __aenter__(self) -> _MockWS:
        return self._ws

    async def __aexit__(self, *exc: object) -> None:
        await self._ws.close()


def _make_factory(
    ws: _MockWS,
) -> Callable[[str], Awaitable[_CM]]:
    async def factory(url: str, **kw: Any) -> _CM:
        ws.recv_kwargs.append(kw)
        return _CM(ws)

    return factory


async def test_recording_transport_wraps_live_transport(tmp_path: pathlib.Path) -> None:
    """RecordingTransport(LiveTransport, JsonlRecorder) is the Phase 4 use case."""
    dst = tmp_path / "live.jsonl"

    # Time-sync first (so ClockOffset updates + time-sync routing works), then initial-state.
    frames = [
        {"type": "time", "value": 1_700_000_000_000},
        {"PID": 0, "VER": "1.0", "EXPORTID": "evt-1", "TRACKNAME": "N", "RESULTS": []},
    ]
    ws = _MockWS(frames=frames)
    rec = JsonlRecorder(dst)
    live = LiveTransport(
        "evt-1",
        websockets_factory=_make_factory(ws),
        idle_timeout_s=10.0,
        reconnect_policy=ReconnectPolicy(max_attempts=0, initial_offset_s=0),
    )
    rt = RecordingTransport(inner=live, recorder=rec)

    msgs = [m async for m in rt]
    await rt.close()

    # Only the InitialStateMessage is yielded — time-sync is filtered by LiveTransport
    assert len(msgs) == 1
    assert isinstance(msgs[0], InitialStateMessage)
    # 1 message on disk (time-sync excluded)
    assert await asyncio.to_thread(_exists, dst)
    content = await asyncio.to_thread(_read_text, dst)
    lines = [ln for ln in content.strip().split("\n") if ln.strip()]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["event_pid"] == 0
