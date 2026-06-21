"""Tests for the nls-replay CLI (cli/replay.py).

The tests build small hand-crafted JSONL files in tmp_path and exercise
the public ``run()`` and ``main()`` entry points without touching the
network. Most tests use the ``out=StringIO()`` kwarg to capture stdout
without the test runner competing with the CLI's own prints.

Test coverage (D-03..D-05, D-25):

- basic three-message replay prints one repr per Message (D-03)
- ``--limit`` stops after N messages
- ``--speed 0`` is a burst (no real-time delay)
- ``--summary`` prints the per-pid breakdown block (D-05)
- empty file exits 0 by default; exits 1 with ``--strict``
- UnknownMessage default mode continues + WARNING; strict raises + exits 1
- malformed line (missing ``raw``) strict mode raises ReplaySchemaError
- ``--help`` exits 0 and shows all five flags
- ``speed_factor=-1`` rejected by ReplayTransport (ValueError)
"""

from __future__ import annotations

import json
import sys
import time
from io import StringIO
from pathlib import Path

import pytest

from aionlslivetiming.cli import replay

# -- Fixtures ---------------------------------------------------------------------


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "messages"


def _load_fixture(name: str) -> dict[str, object]:
    """Load a JSON fixture file by name from tests/fixtures/messages/."""
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _write_jsonl(path: Path, lines: list[dict[str, object]]) -> Path:
    """Write a list of dicts as JSONL in the standard {ts_recv_ms, raw} shape.

    Each ``lines[i]`` is expected to be the ``raw`` payload (the eventPid
    lives inside it). A default ``ts_recv_ms`` sequence is assigned so
    the file is monotonic and speed_factor works normally.
    """
    with path.open("w", encoding="utf-8") as fh:
        ts = 1000
        for raw in lines:
            fh.write(
                json.dumps({"ts_recv_ms": ts, "raw": raw}, separators=(",", ":"))
                + "\n"
            )
            ts += 1000
    return path


# -- Basic replay (D-03) ----------------------------------------------------------


async def test_replay_basic_three_messages(tmp_path: Path) -> None:
    """A 3-line JSONL (PID 0 + PID 4 + PID 3) prints 3 lines, exits 0."""
    jsonl = _write_jsonl(
        tmp_path / "replay.jsonl",
        [
            _load_fixture("pid_0_initial.json"),
            _load_fixture("pid_4_track_state_running.json"),
            _load_fixture("pid_3_race_message_flag.json"),
        ],
    )
    out = StringIO()
    rc = await replay.run(jsonl, out=out)
    assert rc == 0
    lines = out.getvalue().splitlines()
    assert len(lines) == 3
    # Sanity: each line is a non-empty dataclass repr
    for line in lines:
        assert line.startswith("InitialStateMessage(") or line.startswith(
            "TrackStateMessage("
        ) or line.startswith("RaceMessage(")


# -- --limit ----------------------------------------------------------------------


async def test_replay_limit_two_stops_after_two(tmp_path: Path) -> None:
    """``--limit 2`` stops after 2 messages, exit code 0."""
    jsonl = _write_jsonl(
        tmp_path / "replay.jsonl",
        [
            _load_fixture("pid_0_initial.json"),
            _load_fixture("pid_4_track_state_running.json"),
            _load_fixture("pid_3_race_message_flag.json"),
        ],
    )
    out = StringIO()
    rc = await replay.run(jsonl, limit=2, out=out)
    assert rc == 0
    lines = out.getvalue().splitlines()
    assert len(lines) == 2


# -- --speed ----------------------------------------------------------------------


async def test_replay_speed_factor_zero_is_burst(tmp_path: Path) -> None:
    """``--speed 0`` emits messages without real-time delay (burst)."""
    # 3 lines spaced 500ms apart in ts_recv_ms
    path = tmp_path / "replay.jsonl"
    path.write_text(
        '{"ts_recv_ms": 1000, "raw": '
        + json.dumps(_load_fixture("pid_0_initial.json"))
        + "}\n"
        + '{"ts_recv_ms": 1500, "raw": '
        + json.dumps(_load_fixture("pid_4_track_state_running.json"))
        + "}\n"
        + '{"ts_recv_ms": 2000, "raw": '
        + json.dumps(_load_fixture("pid_3_race_message_flag.json"))
        + "}\n",
        encoding="utf-8",
    )
    out = StringIO()
    started = time.monotonic()
    rc = await replay.run(path, speed_factor=0, out=out)
    elapsed = time.monotonic() - started
    assert rc == 0
    assert len(out.getvalue().splitlines()) == 3
    # Burst: real-time replay of 500ms+500ms = 1.0s; speed=0 must be < 200ms
    assert elapsed < 0.5, f"speed_factor=0 took {elapsed:.3f}s, expected burst"


async def test_replay_speed_factor_validation() -> None:
    """``speed_factor=-1`` raises ValueError (delegated to ReplayTransport)."""
    out = StringIO()
    with pytest.raises(ValueError, match="speed_factor"):
        await replay.run(
            Path("/tmp/doesnt-matter.jsonl"),
            speed_factor=-1,
            out=out,
        )


# -- --summary --------------------------------------------------------------------


async def test_replay_summary_block_format(tmp_path: Path) -> None:
    """``--summary`` appends a structured block: total / per-pid / ts range."""
    jsonl = _write_jsonl(
        tmp_path / "replay.jsonl",
        [
            _load_fixture("pid_0_initial.json"),
            _load_fixture("pid_4_track_state_running.json"),
            _load_fixture("pid_3_race_message_flag.json"),
        ],
    )
    out = StringIO()
    rc = await replay.run(jsonl, summary=True, out=out)
    assert rc == 0
    text = out.getvalue()
    assert "--- nls-replay summary ---" in text
    assert "per eventPid:" in text
    assert "UnknownMessage count: 0" in text
    assert "first ts_recv_ms: 1000" in text
    assert "last ts_recv_ms: 3000" in text
    assert "total messages: 3" in text


async def test_replay_summary_with_unknown_message(tmp_path: Path) -> None:
    """``--summary`` counts UnknownMessage in the breakdown."""
    path = tmp_path / "replay.jsonl"
    path.write_text(
        '{"ts_recv_ms": 1000, "raw": '
        + json.dumps(_load_fixture("pid_0_initial.json"))
        + "}\n"
        + '{"ts_recv_ms": 2000, "raw": '
        + json.dumps(_load_fixture("unknown_pid.json"))
        + "}\n",
        encoding="utf-8",
    )
    out = StringIO()
    rc = await replay.run(path, summary=True, out=out)
    assert rc == 0
    text = out.getvalue()
    assert "UnknownMessage count: 1" in text
    assert "total messages: 2" in text


# -- Empty file ------------------------------------------------------------------


async def test_replay_empty_file_exits_zero_default(tmp_path: Path) -> None:
    """Empty JSONL: default mode exits 0, WARNING logged."""
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    out = StringIO()
    rc = await replay.run(path, out=out)
    # ReplayEmptyError is caught and logged; default exits 0
    assert rc == 0
    assert out.getvalue() == ""


async def test_replay_empty_file_strict_exits_one(tmp_path: Path) -> None:
    """Empty JSONL + ``--strict`` exits 1 (ReplayEmptyError caught, strict returns 1)."""
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    out = StringIO()
    rc = await replay.run(path, strict=True, out=out)
    assert rc == 1


# -- UnknownMessage (D-25) -------------------------------------------------------


async def test_replay_unknown_message_default_continues(tmp_path: Path) -> None:
    """UnknownMessage + default mode: continues, exits 0."""
    path = tmp_path / "replay.jsonl"
    path.write_text(
        '{"ts_recv_ms": 1000, "raw": '
        + json.dumps(_load_fixture("unknown_pid.json"))
        + "}\n",
        encoding="utf-8",
    )
    out = StringIO()
    rc = await replay.run(path, out=out)
    assert rc == 0
    # One line written (the UnknownMessage repr)
    assert len(out.getvalue().splitlines()) == 1
    assert "UnknownMessage" in out.getvalue()


async def test_replay_unknown_message_strict_returns_one(tmp_path: Path) -> None:
    """UnknownMessage + ``--strict``: returns 1."""
    path = tmp_path / "replay.jsonl"
    path.write_text(
        '{"ts_recv_ms": 1000, "raw": '
        + json.dumps(_load_fixture("unknown_pid.json"))
        + "}\n",
        encoding="utf-8",
    )
    out = StringIO()
    rc = await replay.run(path, strict=True, out=out)
    assert rc == 1


# -- Malformed line: ReplaySchemaError -------------------------------------------


async def test_replay_malformed_line_schema_error_strict_returns_one(
    tmp_path: Path,
) -> None:
    """A line missing the ``raw`` key in ``--strict`` mode returns 1."""
    path = tmp_path / "replay.jsonl"
    # No 'raw' key — triggers ReplaySchemaError from the transport.
    path.write_text('{"ts_recv_ms": 1000, "oops": true}\n', encoding="utf-8")
    out = StringIO()
    rc = await replay.run(path, strict=True, out=out)
    assert rc == 1


async def test_replay_malformed_line_default_returns_zero(tmp_path: Path) -> None:
    """A malformed line in default mode is caught and returns 0."""
    path = tmp_path / "replay.jsonl"
    path.write_text('{"ts_recv_ms": 1000, "oops": true}\n', encoding="utf-8")
    out = StringIO()
    rc = await replay.run(path, out=out)
    assert rc == 0


# -- --show-time-sync ------------------------------------------------------------


async def test_replay_show_time_sync_no_op_when_suppressed(
    tmp_path: Path,
) -> None:
    """ReplayTransport suppresses time-sync by default; --show-time-sync is a no-op."""
    jsonl = _write_jsonl(
        tmp_path / "replay.jsonl",
        [_load_fixture("pid_0_initial.json")],
    )
    out = StringIO()
    rc = await replay.run(jsonl, show_time_sync=True, out=out)
    assert rc == 0
    # The PID 0 message is still emitted
    assert len(out.getvalue().splitlines()) == 1


# -- main() tests -----------------------------------------------------------------


def test_replay_main_parses_args_and_invokes_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main`` parses argv and delegates to ``asyncio.run(run)``."""
    captured: dict[str, object] = {}

    async def _fake_run(**kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(replay, "run", _fake_run)
    monkeypatch.setattr(
        sys, "argv", ["nls-replay", "/tmp/x.jsonl", "--summary", "--strict"]
    )

    rc = replay.main()
    assert rc == 0
    assert captured.get("path") == "/tmp/x.jsonl"
    assert captured.get("summary") is True
    assert captured.get("strict") is True


def test_replay_help_includes_all_flags() -> None:
    """``--help`` exits 0 and mentions all five CLI flags."""
    with pytest.raises(SystemExit) as exc:
        replay.main(["--help"])
    assert exc.value.code == 0


def test_replay_help_text_contains_flags(capsys: pytest.CaptureFixture[str]) -> None:
    """The ``--help`` output explicitly lists every D-03..D-05 flag."""
    with pytest.raises(SystemExit):
        replay.main(["--help"])
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    for flag in ("--speed", "--limit", "--show-time-sync", "--strict", "--summary"):
        assert flag in combined, f"flag {flag!r} missing from --help output"


# -- Module surface tests ---------------------------------------------------------


def test_replay_module_exports_main_and_run() -> None:
    """``cli.replay`` exposes ``main`` and ``run`` (D-01 contract)."""
    assert callable(replay.main)
    assert callable(replay.run)


def test_replay_main_uses_prog_nls_replay() -> None:
    """``argparse`` is built with ``prog='nls-replay'`` (D-01 contract)."""
    # Build a parser with the same kwargs to inspect prog.
    parser = replay.argparse.ArgumentParser(prog="nls-replay")
    assert parser.prog == "nls-replay"
