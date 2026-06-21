"""Tests for JsonlRecorder — append-only, async-isolated, round-trip."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest

from aionlslivetiming.events import (
    InitialStateMessage,
    TimeSyncMessage,
)
from aionlslivetiming.transport import JsonlRecorder, ReplayTransport

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator


def make_initial_msg() -> InitialStateMessage:
    """Build a minimal InitialStateMessage for the test fixture.

    The ``raw`` payload is the *original* server short-code JSON that the
    parser produced this Message from. Round-trip via JsonlRecorder →
    ReplayTransport uses ``raw`` to re-parse (D-10 invariant), so a
    complete ``raw`` is required for the round-trip test to recover the
    typed shape.
    """
    return InitialStateMessage(
        pid=0,
        ver="1.0",
        export_id="evt-1",
        track_name="Nordschleife",
        session=None,
        results=(),
        best_sectors=(),
        raw={
            "eventPid": 0,
            "PID": 0,
            "VER": "1.0",
            "EXPORTID": "evt-1",
            "TRACKNAME": "Nordschleife",
            "RESULTS": [],
        },
    )


def make_time_sync_msg() -> TimeSyncMessage:
    """Build a TimeSyncMessage for the test fixture."""
    return TimeSyncMessage(value_ms=1_700_000_000_000)


@pytest.fixture
async def tmp_jsonl(tmp_path: pathlib.Path) -> AsyncIterator[pathlib.Path]:
    """Yield a temp JSONL path; pytest tmp_path handles cleanup."""
    p = tmp_path / "out.jsonl"
    yield p


def _read_text(p: pathlib.Path) -> str:
    """Sync read helper — kept tiny so the test does not block the event loop meaningfully."""
    return p.read_text()


async def test_recorder_writes_phase3_schema(tmp_jsonl: pathlib.Path) -> None:
    """Each line is {ts_recv_ms, event_pid, raw, parsed}."""
    rec = JsonlRecorder(tmp_jsonl)
    await rec.append(make_initial_msg())
    await rec.append(make_time_sync_msg())
    await rec.close()

    text = await asyncio.to_thread(_read_text, tmp_jsonl)
    lines = text.strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        obj = json.loads(line)
        assert "ts_recv_ms" in obj and isinstance(obj["ts_recv_ms"], int)
        assert "event_pid" in obj and isinstance(obj["event_pid"], int)
        assert "raw" in obj
        assert "parsed" in obj


async def test_recorder_round_trips_with_replay(tmp_jsonl: pathlib.Path) -> None:
    """What JsonlRecorder writes, ReplayTransport reads back (re-parse raw)."""
    rec = JsonlRecorder(tmp_jsonl)
    await rec.append(make_initial_msg())
    await rec.close()

    rt = ReplayTransport(tmp_jsonl, suppress_time_sync=True)
    await rt.connect()
    msgs = [m async for m in rt]
    assert len(msgs) == 1
    assert isinstance(msgs[0], InitialStateMessage)
    assert msgs[0].event_pid == 0


async def test_recorder_concurrent_appends_no_interleave(tmp_jsonl: pathlib.Path) -> None:
    """20 coroutines append 10 messages each — every line is well-formed JSON."""
    rec = JsonlRecorder(tmp_jsonl)

    async def appender(start: int) -> None:
        for _ in range(10):
            await rec.append(make_initial_msg())  # all same shape; tests ordering

    await asyncio.gather(*(appender(i) for i in range(20)))
    await rec.close()

    text = await asyncio.to_thread(_read_text, tmp_jsonl)
    lines = text.strip().split("\n")
    assert len(lines) == 200
    for line in lines:
        obj = json.loads(line)  # would raise on partial line
        assert "event_pid" in obj


async def test_recorder_close_is_idempotent(tmp_jsonl: pathlib.Path) -> None:
    """Calling close() twice is safe."""
    rec = JsonlRecorder(tmp_jsonl)
    await rec.append(make_initial_msg())
    await rec.close()
    await rec.close()  # no error
    assert await asyncio.to_thread(tmp_jsonl.exists)


async def test_recorder_append_after_close_raises(tmp_jsonl: pathlib.Path) -> None:
    """append() after close() raises RuntimeError."""
    rec = JsonlRecorder(tmp_jsonl)
    await rec.close()
    with pytest.raises(RuntimeError):
        await rec.append(make_initial_msg())


async def test_recorder_context_manager(tmp_jsonl: pathlib.Path) -> None:
    """async with JsonlRecorder(...) as rec: ... flushes on exit."""
    async with JsonlRecorder(tmp_jsonl) as rec:
        await rec.append(make_initial_msg())
    assert await asyncio.to_thread(tmp_jsonl.exists)
    text = await asyncio.to_thread(_read_text, tmp_jsonl)
    assert len(text.strip().split("\n")) == 1


async def test_recorder_creates_parent_dirs(tmp_path: pathlib.Path) -> None:
    """Recorders in non-existent parent directories create the path."""
    nested = tmp_path / "a" / "b" / "c" / "out.jsonl"
    rec = JsonlRecorder(nested)
    await rec.append(make_initial_msg())
    await rec.close()
    assert await asyncio.to_thread(nested.exists)


async def test_recorder_reopen_appends(tmp_jsonl: pathlib.Path) -> None:
    """Reopening a JsonlRecorder on the same path appends to existing content."""
    rec = JsonlRecorder(tmp_jsonl)
    await rec.append(make_initial_msg())
    await rec.close()

    rec2 = JsonlRecorder(tmp_jsonl)
    await rec2.append(make_initial_msg())
    await rec2.close()

    text = await asyncio.to_thread(_read_text, tmp_jsonl)
    lines = text.strip().split("\n")
    assert len(lines) == 2


async def test_recorder_parsed_field_round_trips(tmp_jsonl: pathlib.Path) -> None:
    """The `parsed` field of each line is JSON-serialisable."""
    rec = JsonlRecorder(tmp_jsonl)
    await rec.append(make_initial_msg())
    await rec.close()

    text = await asyncio.to_thread(_read_text, tmp_jsonl)
    line = text.strip()
    obj = json.loads(line)
    # parsed is a dict-as-JSON of the dataclass; track_name should round-trip
    assert obj["parsed"]["track_name"] == "Nordschleife"
    assert obj["parsed"]["export_id"] == "evt-1"


async def test_recorder_writes_correct_event_pids(tmp_jsonl: pathlib.Path) -> None:
    """event_pid matches the Message type's classvar / instance field."""
    rec = JsonlRecorder(tmp_jsonl)
    await rec.append(make_initial_msg())  # event_pid = 0
    await rec.append(make_time_sync_msg())  # event_pid = -1
    await rec.close()

    text = await asyncio.to_thread(_read_text, tmp_jsonl)
    lines = text.strip().split("\n")
    pids = [json.loads(ln)["event_pid"] for ln in lines]
    assert pids == [0, -1]
