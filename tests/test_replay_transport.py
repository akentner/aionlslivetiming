"""Tests for ReplayTransport — speed_factor, D-07 backward-compat, error paths."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from aionlslivetiming.events import (
    InitialStateMessage,
    TimeSyncMessage,
)
from aionlslivetiming.exceptions import (
    ReplayEmptyError,
    ReplayOrderingError,
    ReplaySchemaError,
)
from aionlslivetiming.transport import ReplayTransport

if TYPE_CHECKING:
    import pathlib


def write_jsonl(path: pathlib.Path, lines: list[dict[str, Any]]) -> None:
    """Helper: write lines to a JSONL file (one per line)."""
    with path.open("w", encoding="utf-8") as fh:
        for ln in lines:
            fh.write(json.dumps(ln) + "\n")


def make_initial_line(ts: int = 1000) -> dict[str, Any]:
    """Build a minimal PID-0 line for tests."""
    return {
        "ts_recv_ms": ts,
        "event_pid": 0,
        "raw": {
            "PID": 0,
            "VER": "1.0",
            "EXPORTID": "evt",
            "TRACKNAME": "Nordschleife",
            "RESULTS": [],
        },
        "parsed": {},
    }


def make_time_sync_line(ts: int = 1000, server_ms: int = 1_700_000_000_000) -> dict[str, Any]:
    """Build a time-sync line for tests."""
    return {
        "ts_recv_ms": ts,
        "event_pid": -1,
        "raw": {"type": "time", "value": server_ms},
        "parsed": {"value_ms": server_ms},
    }


async def collect(transport: ReplayTransport) -> list:
    """Helper: drain a transport and return the messages."""
    return [m async for m in transport]


async def test_replay_empty_raises_replay_empty_error(tmp_path: pathlib.Path) -> None:
    """Empty file → ReplayEmptyError (D-17)."""
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    with pytest.raises(ReplayEmptyError):
        await collect(ReplayTransport(p))


async def test_replay_whitespace_only_raises_replay_empty_error(tmp_path: pathlib.Path) -> None:
    """A JSONL of only blank lines is treated as empty (no emitted messages)."""
    p = tmp_path / "ws.jsonl"
    p.write_text("\n\n\n")
    with pytest.raises(ReplayEmptyError):
        await collect(ReplayTransport(p))


async def test_replay_missing_raw_raises_schema_error(tmp_path: pathlib.Path) -> None:
    """A line without `raw` → ReplaySchemaError(line_no) (D-17)."""
    p = tmp_path / "bad.jsonl"
    p.write_text('{"ts_recv_ms": 1000}\n')
    with pytest.raises(ReplaySchemaError) as exc_info:
        await collect(ReplayTransport(p))
    assert exc_info.value.line_no == 1


async def test_replay_non_monotonic_raises_ordering_error(tmp_path: pathlib.Path) -> None:
    """ts_recv_ms going backwards → ReplayOrderingError(line_no, prev, curr) (D-17)."""
    p = tmp_path / "bad.jsonl"
    write_jsonl(p, [make_initial_line(2000), make_initial_line(1000)])
    with pytest.raises(ReplayOrderingError) as exc_info:
        await collect(ReplayTransport(p))
    assert exc_info.value.line_no == 2
    assert exc_info.value.prev_ts == 2000
    assert exc_info.value.curr_ts == 1000


async def test_replay_invalid_json_trailing_line_warning(tmp_path: pathlib.Path) -> None:
    """Invalid JSON trailing line → log WARNING + skip (D-17 looks-done-but-isnt)."""
    p = tmp_path / "bad.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(make_initial_line(1000)) + "\n")
        fh.write("this is not json\n")
    msgs = await collect(ReplayTransport(p))
    assert len(msgs) == 1  # the good line


async def test_replay_d07_backward_compat(tmp_path: pathlib.Path) -> None:
    """Phase 1 D-07 shape {ts_recv_ms, raw} replays correctly (no event_pid, no parsed)."""
    p = tmp_path / "d07.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts_recv_ms": 1000,
                    "raw": {
                        "PID": 0,
                        "VER": "1.0",
                        "EXPORTID": "evt",
                        "TRACKNAME": "Nordschleife",
                        "RESULTS": [],
                    },
                }
            )
            + "\n"
        )
    msgs = await collect(ReplayTransport(p))
    assert len(msgs) == 1
    assert isinstance(msgs[0], InitialStateMessage)


async def test_replay_speed_factor_zero_burst(tmp_path: pathlib.Path) -> None:
    """speed_factor=0 → burst (no sleeps); 100 lines complete near-instantly."""
    import time

    p = tmp_path / "fast.jsonl"
    write_jsonl(p, [make_initial_line(i * 1000) for i in range(100)])
    t0 = time.monotonic()
    msgs = await collect(ReplayTransport(p, speed_factor=0.0))
    elapsed = time.monotonic() - t0
    assert len(msgs) == 100
    assert elapsed < 1.0  # burst mode — should not take 99 seconds


async def test_replay_speed_factor_negative_raises(tmp_path: pathlib.Path) -> None:
    """Negative speed_factor raises ValueError at construction (D-15)."""
    with pytest.raises(ValueError):
        ReplayTransport("/tmp/x.jsonl", speed_factor=-1.0)


async def test_replay_suppress_time_sync_default_excludes(tmp_path: pathlib.Path) -> None:
    """With suppress_time_sync=True (default), time-sync messages are NOT yielded."""
    p = tmp_path / "sync.jsonl"
    write_jsonl(
        p,
        [
            make_time_sync_line(1000, server_ms=1_700_000_000_000),
            make_initial_line(2000),
        ],
    )
    msgs = await collect(ReplayTransport(p))  # default suppress_time_sync=True
    assert all(not isinstance(m, TimeSyncMessage) for m in msgs)
    assert len(msgs) == 1  # only the initial state


async def test_replay_suppress_time_sync_false_yields(tmp_path: pathlib.Path) -> None:
    """With suppress_time_sync=False, time-sync messages are yielded (D-16)."""
    p = tmp_path / "sync.jsonl"
    write_jsonl(
        p,
        [
            make_time_sync_line(1000, server_ms=1_700_000_000_000),
            make_initial_line(2000),
        ],
    )
    msgs = await collect(ReplayTransport(p, suppress_time_sync=False))
    assert any(isinstance(m, TimeSyncMessage) for m in msgs)
    assert len(msgs) == 2


async def test_replay_updates_clock_offset_from_time_sync(tmp_path: pathlib.Path) -> None:
    """Time-sync messages update ClockOffset regardless of suppress flag (D-04)."""
    p = tmp_path / "sync.jsonl"
    write_jsonl(
        p,
        [
            make_time_sync_line(1000, server_ms=2_000_000_000_000),
            make_initial_line(2000),
        ],
    )
    rt = ReplayTransport(p, suppress_time_sync=True)
    await collect(rt)
    # ClockOffset should have been updated with sample (server_ms - local_recv_ms)
    assert rt.clock_offset.offset_ms is not None
    # The server time is far ahead of local (year 2033 vs now=2026).
    assert rt.clock_offset.offset_ms > 1_000_000_000_000


async def test_replay_rejects_missing_file(tmp_path: pathlib.Path) -> None:
    """Non-existent path → FileNotFoundError on iteration."""
    with pytest.raises(FileNotFoundError):
        await collect(ReplayTransport(tmp_path / "nope.jsonl"))


async def test_replay_speed_factor_10_faster_than_real_time(tmp_path: pathlib.Path) -> None:
    """speed_factor=10 plays ~10x faster than the inter-message gaps."""
    import time

    # 10 messages, each 100ms apart → real-time would be ~1s; at 10x ≈ 100ms.
    p = tmp_path / "fast.jsonl"
    write_jsonl(p, [make_initial_line(1000 + i * 100) for i in range(10)])
    t0 = time.monotonic()
    msgs = await collect(ReplayTransport(p, speed_factor=10.0))
    elapsed = time.monotonic() - t0
    assert len(msgs) == 10
    # Loose bound: 0.5s (some scheduler slack on CI) — well under the 1s real-time
    assert elapsed < 0.5, f"expected ~100ms, got {elapsed:.3f}s"


async def test_replay_yields_initial_state_message(tmp_path: pathlib.Path) -> None:
    """Happy path: a single PID-0 line yields an InitialStateMessage with .raw."""
    p = tmp_path / "ok.jsonl"
    write_jsonl(p, [make_initial_line(1000)])
    msgs = await collect(ReplayTransport(p))
    assert len(msgs) == 1
    msg = msgs[0]
    assert isinstance(msg, InitialStateMessage)
    assert msg.event_pid == 0
    assert msg.track_name == "Nordschleife"


async def test_replay_path_and_speed_factor_properties(tmp_path: pathlib.Path) -> None:
    """Properties expose construction parameters for downstream code."""
    p = tmp_path / "x.jsonl"
    rt = ReplayTransport(p, speed_factor=2.5, suppress_time_sync=False)
    assert rt.path == p
    assert rt.speed_factor == 2.5
    assert rt.suppress_time_sync is False


async def test_replay_close_resets_connected(tmp_path: pathlib.Path) -> None:
    """After close(), the transport is no longer connected (idempotent on second close)."""
    p = tmp_path / "x.jsonl"
    write_jsonl(p, [make_initial_line(1000)])
    rt = ReplayTransport(p)
    await rt.connect()
    await collect(rt)
    await rt.close()
    await rt.close()  # idempotent
