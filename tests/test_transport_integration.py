"""End-to-end integration tests for the Phase 3 transport stack.

These tests exercise the load-bearing invariants:

1. A JSONL written by JsonlRecorder reads back identically through ReplayTransport
   (REC-03: write → read → equal typed Message instances).
2. A RecordingTransport wrapping a LiveTransport writes messages to disk in real
   time (Pitfall #11 invariant: recorder is never behind the iterator).
3. All Transport implementations satisfy the Protocol (runtime_checkable).
4. Race messages survive the round-trip with both ``eventPid`` and ``PID`` keys
   (real server payloads carry both).
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from aionlslivetiming.events import (
    InitialStateMessage,
    PerCarLapsMessage,
    QualifyingMessage,
    RaceMessage,
    StatisticsMessage,
    TrackStateMessage,
)
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


def _dumps(obj: Any) -> str:
    """JSON encode a dict to a string (mimics what real websockets yields)."""
    try:
        import orjson

        return orjson.dumps(obj).decode("utf-8")
    except ImportError:
        import json as _stdlib

        return _stdlib.dumps(obj, separators=(",", ":"))


def _read_text(p: pathlib.Path) -> str:
    """Sync helper for asyncio.to_thread (silences ruff ASYNC240)."""
    return p.read_text(encoding="utf-8")


def _exists(p: pathlib.Path) -> bool:
    return p.exists()


def _count_lines(p: pathlib.Path) -> int:
    """Return the number of non-empty lines in *p* (0 if it does not exist)."""
    if not p.exists():
        return 0
    text = p.read_text(encoding="utf-8")
    return len([ln for ln in text.split("\n") if ln.strip()])


def write_realistic_jsonl(path: pathlib.Path) -> None:
    """Write a 5-line JSONL that exercises all major PIDs (round-trippable).

    The ``raw`` payload is shaped to match what the parser actually expects —
    ``eventPid`` for routing AND ``PID`` (short-code key) for the inner parser.
    Per-car-laps PID 7 uses ``session``/``startingNo``/``laps``; qualifying
    PID 501 uses ``RESULT``; statistics PID 9002 uses ``LEADING``/``BEST_LAPS``/
    ``BEST_SECTORS``.
    """
    lines = [
        {  # PID 0: initial state
            "ts_recv_ms": 1000,
            "raw": {
                "eventPid": 0,
                "PID": 0,
                "VER": "1.0",
                "EXPORTID": "NLS-1",
                "TRACKNAME": "Nordschleife",
                "RESULTS": [
                    {
                        "StartingNo": 7,
                        "Position": 1,
                        "ClassName": "SP9",
                        "Driver": "M. Mueller",
                    }
                ],
            },
        },
        {  # PID 4: track state
            "ts_recv_ms": 2000,
            "raw": {
                "eventPid": 4,
                "PID": 4,
                "VER": "1.0",
                "TRACKSTATE": "GREEN",
                "TIMESTATE": "RUNNING",
                "TOD": {"value": 43200000},
            },
        },
        {  # PID 3: race control message (parser uses ``text``/``type``, not TEXT/CATEGORY)
            "ts_recv_ms": 3000,
            "raw": {
                "eventPid": 3,
                "PID": 3,
                "VER": "1.0",
                "text": "Pit stop",
                "type": "INFO",
                "session": "R1",
                "startingNo": 7,
            },
        },
        {  # PID 7: per-car laps
            "ts_recv_ms": 4000,
            "raw": {
                "eventPid": 7,
                "PID": 7,
                "VER": "1.0",
                "session": "R1",
                "startingNo": 7,
                "laps": [
                    {"lapNo": 1, "lapTime": 162340, "sectors": [58120, 58720, 45500]},
                    {"lapNo": 2, "lapTime": 161900, "sectors": [58000, 58600, 45300]},
                ],
            },
        },
        {  # PID 9002: statistics
            "ts_recv_ms": 5000,
            "raw": {
                "eventPid": 9002,
                "PID": 9002,
                "VER": "1.0",
                "LEADING": [{"StartingNo": 7, "Position": 1}],
                "BEST_LAPS": [{"StartingNo": 7, "Value": 161900}],
                "BEST_SECTORS": [
                    {"STARTINGNO": 7, "SECTOR": 1, "VALUE": 58000},
                ],
            },
        },
    ]
    with path.open("w", encoding="utf-8") as fh:
        for ln in lines:
            fh.write(json.dumps(ln) + "\n")


# ---------- round-trip invariant ----------


async def test_round_trip_recorder_to_replay_preserves_messages(
    tmp_path: pathlib.Path,
) -> None:
    """REC-03: JsonlRecorder writes a file that ReplayTransport reads back as
    the same typed Message instances (same class + same event_pid)."""
    src = tmp_path / "src.jsonl"
    dst = tmp_path / "dst.jsonl"
    write_realistic_jsonl(src)

    # Step 1: read the source and write a copy through the recorder.
    rec = JsonlRecorder(dst)
    rt = RecordingTransport(inner=ReplayTransport(src), recorder=rec)
    original_msgs = [m async for m in rt]
    await rt.close()

    # Step 2: read back what we just recorded.
    replay = ReplayTransport(dst, suppress_time_sync=True)
    replayed_msgs = [m async for m in replay]

    # Same count, same types, same event_pids.
    assert len(original_msgs) == 5
    assert len(replayed_msgs) == 5
    expected_types = [
        InitialStateMessage,
        TrackStateMessage,
        RaceMessage,
        PerCarLapsMessage,
        StatisticsMessage,
    ]
    for orig, rep, expected_type in zip(original_msgs, replayed_msgs, expected_types, strict=True):
        assert type(orig) is type(rep) is expected_type, (
            f"expected {expected_type.__name__}, got {type(orig).__name__} / {type(rep).__name__}"
        )
        assert orig.event_pid == rep.event_pid


async def test_round_trip_via_recorder_then_replay_produces_qualifying_too(
    tmp_path: pathlib.Path,
) -> None:
    """PID 501 (qualifying) also survives the round-trip — covers a channel not
    exercised by the main round-trip test."""
    src = tmp_path / "qual.jsonl"
    dst = tmp_path / "qual_out.jsonl"
    src.write_text(
        json.dumps(
            {
                "ts_recv_ms": 100,
                "raw": {
                    "eventPid": 501,
                    "PID": 501,
                    "VER": "1.0",
                    "RESULT": [
                        {"StartingNo": 7, "Position": 1, "ClassName": "SP9", "best": 161900},
                        {"StartingNo": 12, "Position": 2, "ClassName": "SP9", "best": 162300},
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rec = JsonlRecorder(dst)
    rt = RecordingTransport(inner=ReplayTransport(src), recorder=rec)
    originals = [m async for m in rt]
    await rt.close()

    replayed = [m async for m in ReplayTransport(dst, suppress_time_sync=True)]

    assert len(originals) == 1
    assert isinstance(originals[0], QualifyingMessage)
    assert len(replayed) == 1
    assert isinstance(replayed[0], QualifyingMessage)
    assert originals[0].event_pid == replayed[0].event_pid == 501


# ---------- Live + Recording end-to-end ----------


class _MockWS:
    """Scripted-frames fake for the LiveTransport tests."""

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


async def test_recording_live_yields_and_persists_in_real_time(
    tmp_path: pathlib.Path,
) -> None:
    """Pitfall #11 invariant: every message yielded by RecordingTransport has
    already been written to disk by the wrapped JsonlRecorder."""
    dst = tmp_path / "live.jsonl"

    # Time-sync first (so ClockOffset updates) — the messages() iterator
    # suppresses time-sync, so the disk only carries the InitialStateMessage
    # + TrackStateMessage.
    frames = [
        {"type": "time", "value": 1_700_000_000_000},
        {
            "eventPid": 0,
            "PID": 0,
            "VER": "1.0",
            "EXPORTID": "evt-1",
            "TRACKNAME": "Nordschleife",
            "RESULTS": [{"StartingNo": 7, "Position": 1}],
        },
        {
            "eventPid": 4,
            "PID": 4,
            "VER": "1.0",
            "TRACKSTATE": "GREEN",
            "TIMESTATE": "RUNNING",
        },
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

    yielded: list[Any] = []
    async for m in rt:
        yielded.append(m)
        # Pitfall #7 contract: ``append()`` has been awaited (recorder has the
        # message queued), so the writer task will eventually flush it. Yield
        # control to give the writer task a chance to drain before asserting.
        await asyncio.sleep(0)
        recorded_so_far = await asyncio.to_thread(_count_lines, dst)
        assert recorded_so_far >= len(yielded), (
            f"recorder behind iterator at msg {len(yielded)}: recorded={recorded_so_far}"
        )
    await rt.close()

    # Final invariant: every yielded message is on disk after close().
    assert await asyncio.to_thread(_exists, dst)

    assert len(yielded) == 2
    assert isinstance(yielded[0], InitialStateMessage)
    assert isinstance(yielded[1], TrackStateMessage)

    # Both on disk after close.
    final_lines = await asyncio.to_thread(_count_lines, dst)
    assert final_lines == 2

    # Each line is well-formed Phase 3 schema.
    content = await asyncio.to_thread(_read_text, dst)
    for line in content.strip().split("\n"):
        obj = json.loads(line)
        assert "ts_recv_ms" in obj
        assert "event_pid" in obj
        assert "raw" in obj
        assert obj["event_pid"] in (0, 4)


async def test_recording_live_recorded_file_replays_through_replay_transport(
    tmp_path: pathlib.Path,
) -> None:
    """Full integration: live frames → RecordingTransport → on-disk JSONL
    → ReplayTransport → same typed Messages."""
    dst = tmp_path / "recorded.jsonl"

    frames = [
        {"type": "time", "value": 1_700_000_000_000},
        {
            "eventPid": 0,
            "PID": 0,
            "VER": "1.0",
            "EXPORTID": "NLS-9",
            "TRACKNAME": "Nordschleife",
            "RESULTS": [{"StartingNo": 99, "Position": 1, "ClassName": "SP9"}],
        },
        {
            "eventPid": 3,
            "PID": 3,
            "VER": "1.0",
            "text": "Pit stop",
            "type": "INFO",
            "session": "R1",
            "startingNo": 99,
        },
    ]
    ws = _MockWS(frames=frames)
    rec = JsonlRecorder(dst)
    live = LiveTransport(
        "NLS-9",
        websockets_factory=_make_factory(ws),
        idle_timeout_s=10.0,
        reconnect_policy=ReconnectPolicy(max_attempts=0, initial_offset_s=0),
    )
    rt = RecordingTransport(inner=live, recorder=rec)

    live_msgs = [m async for m in rt]
    await rt.close()

    replayed = [m async for m in ReplayTransport(dst, suppress_time_sync=True)]

    assert len(live_msgs) == len(replayed) == 2
    assert isinstance(live_msgs[0], InitialStateMessage)
    assert isinstance(replayed[0], InitialStateMessage)
    assert isinstance(live_msgs[1], RaceMessage)
    assert isinstance(replayed[1], RaceMessage)
    for live_m, replay_m in zip(live_msgs, replayed, strict=True):
        assert type(live_m) is type(replay_m)
        assert live_m.event_pid == replay_m.event_pid


# ---------- Protocol satisfaction ----------


def test_all_transports_satisfy_protocol(tmp_path: pathlib.Path) -> None:
    """All four Transport implementations satisfy the Protocol (runtime_checkable).

    JsonlRecorder is intentionally NOT a Transport — it's a writer, not a
    stream. RecordingTransport wrapping any inner Transport is itself a Transport
    (composition is symmetric per ARCHITECTURE.md pattern 2).
    """
    assert isinstance(ReplayTransport(tmp_path / "x.jsonl"), Transport)
    assert isinstance(LiveTransport("evt-1"), Transport)
    assert not isinstance(JsonlRecorder(tmp_path / "y.jsonl"), Transport)

    inner = ReplayTransport(tmp_path / "z.jsonl")
    rec = JsonlRecorder(tmp_path / "w.jsonl")
    assert isinstance(RecordingTransport(inner=inner, recorder=rec), Transport)
