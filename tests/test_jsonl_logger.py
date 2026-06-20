"""Tests for the D-07 JSONL live-capture CLI.

The tests mock ``websockets.connect`` so the test does not hit the network.
The mock returns an async context manager whose ``__aenter__`` produces a
fake WebSocket that yields a fixed list of bytes-frames (or raises the
configured exception).

Each test exercises one branch of :func:`run` plus the CLI surface in
:func:`main`.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from aionlslivetiming.cli import jsonl_logger

if TYPE_CHECKING:
    import pathlib

# -- Async-context-manager helpers -------------------------------------------------


class _FakeWebSocket:
    """A minimal stand-in for a ``websockets.WebSocketClientProtocol``."""

    def __init__(self, frames: list[bytes], recv_exc: BaseException | None = None) -> None:
        self._frames = list(frames)
        self._recv_exc = recv_exc
        self._exc_raised = False
        self.sent: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> bytes:
        # Mirrors ``websockets.WebSocketClientProtocol.recv()`` (no
        # ``timeout`` kwarg — that is ``asyncio.wait_for``'s job). The fake
        # does not actually wait; it just returns pre-queued frames.
        if self._frames:
            return self._frames.pop(0)
        if self._recv_exc is not None and not self._exc_raised:
            self._exc_raised = True
            raise self._recv_exc
        # No more frames and no exception configured — close the connection
        # rather than block forever, so tests don't deadlock when the producer
        # runs out of material.
        raise ConnectionResetError("fake websocket closed (no more frames)")


class _FakeConnectCM:
    """Async context manager returned by the mocked ``websockets.connect``."""

    def __init__(self, ws: _FakeWebSocket) -> None:
        self._ws = ws

    async def __aenter__(self) -> _FakeWebSocket:
        return self._ws

    async def __aexit__(self, *exc_info: Any) -> None:
        return None


def _make_factory(ws: _FakeWebSocket):
    """Build a sync-callable factory that returns a coroutine for *ws*."""

    async def _coro(*args: Any, **kwargs: Any) -> _FakeConnectCM:
        return _FakeConnectCM(ws)

    def _factory(*args: Any, **kwargs: Any):
        return _coro(*args, **kwargs)

    return _factory


# -- run() tests -------------------------------------------------------------------


async def test_run_writes_one_jsonl_line_per_frame(tmp_path: pathlib.Path) -> None:
    """Three frames in -> three JSONL lines out, with ``ts_recv_ms`` and ``raw``."""
    frames = [
        b'{"type":"time","value":100}',
        b'{"eventPid":0,"PID":12345,"RESULT":["a"]}',
        b'{"eventPid":4,"TRACKSTATE":"GREEN"}',
    ]
    ws = _FakeWebSocket(frames)
    out = tmp_path / "out.jsonl"

    rc = await jsonl_logger.run(
        event_id="test-event",
        output_path=out,
        max_seconds=1,
        websockets_factory=_make_factory(ws),
    )

    assert rc == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3

    parsed = [json.loads(line) for line in lines]
    for line in parsed:
        assert isinstance(line["ts_recv_ms"], int)
        assert isinstance(line["raw"], dict)

    assert parsed[0]["raw"] == {"type": "time", "value": 100}
    assert parsed[1]["raw"] == {"eventPid": 0, "PID": 12345, "RESULT": ["a"]}
    assert parsed[2]["raw"] == {"eventPid": 4, "TRACKSTATE": "GREEN"}

    # The handshake should have been sent exactly once, with the wire format
    # matching the JS bundle: ``{"eventId": "<id>", "eventPid": [...], "clientLocalTime": <ms>}``.
    assert len(ws.sent) == 1
    handshake = json.loads(ws.sent[0])
    assert handshake["eventId"] == "test-event"
    assert handshake["eventPid"] == [0, 3, 4, 7, 501, 9002]
    assert isinstance(handshake["clientLocalTime"], int)
    assert handshake["clientLocalTime"] > 0


async def test_run_handles_connection_closed(tmp_path: pathlib.Path) -> None:
    """``ConnectionClosed`` after one frame -> return 0, one line written."""

    class _ConnClosed(Exception):
        """Stand-in for ``websockets.exceptions.ConnectionClosed``."""

    ws = _FakeWebSocket([b'{"eventPid":3,"text":"pit"}'], recv_exc=_ConnClosed())
    out = tmp_path / "out.jsonl"

    rc = await jsonl_logger.run(
        event_id="ev",
        output_path=out,
        websockets_factory=_make_factory(ws),
    )

    assert rc == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) == 1


async def test_run_handles_keyboard_interrupt(tmp_path: pathlib.Path) -> None:
    """Ctrl-C during recv -> return 0 and create the (empty) output file."""
    ws = _FakeWebSocket([], recv_exc=KeyboardInterrupt())
    out = tmp_path / "out.jsonl"

    rc = await jsonl_logger.run(
        event_id="ev",
        output_path=out,
        websockets_factory=_make_factory(ws),
    )

    assert rc == 0
    assert out.exists()


async def test_run_respects_max_seconds_when_server_quiet(tmp_path: pathlib.Path) -> None:
    """``max_seconds`` must fire even if the server sends no further frames.

    The CLI must not block on ``recv()`` past the deadline. A fake WS whose
    ``recv()`` sleeps until cancelled (mimicking a quiet server whose
    underlying transport never produces a frame) lets us assert that
    ``run`` returns 0 within the deadline.
    """

    import asyncio as _asyncio

    class _QuietWebSocket(_FakeWebSocket):
        """Fake WS whose recv() awaits forever — only cancellation unblocks it."""

        def __init__(self) -> None:
            super().__init__([])
            self._call_count = 0

        async def recv(self) -> bytes:  # type: ignore[override]
            self._call_count += 1
            await _asyncio.sleep(60)  # never reached; cancelled by wait_for
            return b""  # pragma: no cover

    ws = _QuietWebSocket()
    out = tmp_path / "out.jsonl"

    import time as _time

    started = _time.monotonic()
    rc = await jsonl_logger.run(
        event_id="ev",
        output_path=out,
        max_seconds=0.2,
        websockets_factory=_make_factory(ws),
    )
    elapsed = _time.monotonic() - started

    assert rc == 0
    assert out.exists()
    # Must not run significantly past the deadline. Allow 2x slack for
    # scheduler jitter on slow CI machines.
    assert elapsed < 1.0, f"run took {elapsed:.2f}s, expected < 1.0s"
    # recv() should have been called at least once before we exited.
    assert ws._call_count >= 1


# -- main() tests ------------------------------------------------------------------


def test_main_parses_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """``main`` parses argv and delegates to ``asyncio.run`` exactly once."""
    calls: list[Any] = []

    def _fake_run(coro: Any) -> int:
        # Close the coroutine to suppress "never awaited" warnings.
        coro.close()
        calls.append(coro)
        return 0

    monkeypatch.setattr(jsonl_logger.asyncio, "run", _fake_run)
    monkeypatch.setattr(sys, "argv", ["jsonl_logger", "E-123", "out.jsonl"])

    rc = jsonl_logger.main()
    assert rc == 0
    assert len(calls) == 1


def test_main_help_exits_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--help`` exits via ``SystemExit(0)``."""
    monkeypatch.setattr(sys, "argv", ["jsonl_logger", "--help"])
    with pytest.raises(SystemExit) as exc:
        jsonl_logger.main()
    assert exc.value.code == 0


def test_run_uses_websockets_module_when_no_factory(tmp_path: pathlib.Path) -> None:
    """Without an explicit factory, ``run`` falls back to the real websockets module."""

    class _CM:
        async def __aenter__(self) -> _FakeWebSocket:
            return _FakeWebSocket([])  # close immediately on first recv

        async def __aexit__(self, *a: Any) -> None:
            return None

    async def _connect(*args: Any, **kwargs: Any) -> _CM:
        return _CM()

    class _FakeWSModule:
        @staticmethod
        async def connect(*args: Any, **kwargs: Any) -> _CM:
            return await _connect(*args, **kwargs)

    with patch.dict(sys.modules, {"websockets": _FakeWSModule}):
        rc = asyncio.run(
            jsonl_logger.run(
                event_id="x",
                output_path=tmp_path / "out.jsonl",
            )
        )
    assert rc == 0
    # File was created (even if empty) and the test exercised the lazy import.
    assert (tmp_path / "out.jsonl").exists()
