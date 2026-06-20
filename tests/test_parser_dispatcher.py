"""Public ``parse()`` dispatcher tests (D-04, D-05, D-06, PARSE-04).

Each test loads a fixture JSON (the public D-08 contract) and asserts
that ``parse()`` returns the correct typed ``Message`` subclass for
each of the 6 known PIDs, the time-sync frame, and the unknown-PID
fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aionlslivetiming.events import (
    InitialStateMessage,
    PerCarLapsMessage,
    QualifyingMessage,
    RaceMessage,
    StatisticsMessage,
    TimeSyncMessage,
    TrackStateMessage,
    UnknownMessage,
)
from aionlslivetiming.parser import parse

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "messages"


def load(name: str) -> dict[str, Any]:
    """Load and JSON-parse a fixture file by name (no .json suffix)."""
    return json.loads((FIXTURES / f"{name}.json").read_text())


def test_dispatch_pid_0() -> None:
    """PID 0 → InitialStateMessage; track_name survives parse."""
    raw = load("pid_0_initial")
    msg = parse(raw)
    assert isinstance(msg, InitialStateMessage)
    assert msg.event_pid == 0
    assert msg.track_name == "Nürburgring Nordschleife"
    assert msg.results[0].starting_no == 7


def test_dispatch_pid_0_lts_not_found() -> None:
    """PID 0 with LTS_NOT_FOUND → InitialStateMessage(lts_not_found=True)."""
    raw = load("pid_0_lts_not_found")
    msg = parse(raw)
    assert isinstance(msg, InitialStateMessage)
    assert msg.lts_not_found is True


def test_dispatch_pid_3_pit() -> None:
    """PID 3 PIT message → RaceMessage with category=='PIT'."""
    raw = load("pid_3_race_message_pit")
    msg = parse(raw)
    assert isinstance(msg, RaceMessage)
    assert msg.event_pid == 3
    assert msg.category == "PIT"
    assert msg.starting_no == 7
    assert msg.session == "R1"


def test_dispatch_pid_3_flag() -> None:
    """PID 3 FLAG message → RaceMessage with category=='FLAG' and no starting_no."""
    raw = load("pid_3_race_message_flag")
    msg = parse(raw)
    assert isinstance(msg, RaceMessage)
    assert msg.category == "FLAG"
    assert msg.starting_no is None
    assert msg.session is None


def test_dispatch_pid_4_running() -> None:
    """PID 4 GREEN/RUNNING → TrackStateMessage with tod set."""
    raw = load("pid_4_track_state_running")
    msg = parse(raw)
    assert isinstance(msg, TrackStateMessage)
    assert msg.event_pid == 4
    assert msg.track_state == "GREEN"
    assert msg.time_state == "RUNNING"
    assert msg.tod is not None
    assert msg.tod.value_ms == 1834000
    assert msg.end_time is None


def test_dispatch_pid_4_finished() -> None:
    """PID 4 CHEQUERED/FINISHED → TrackStateMessage with end_time set."""
    raw = load("pid_4_track_state_finished")
    msg = parse(raw)
    assert isinstance(msg, TrackStateMessage)
    assert msg.track_state == "CHEQUERED"
    assert msg.time_state == "FINISHED"
    assert msg.end_time is not None
    assert msg.end_time.value_ms == 7200000


def test_dispatch_pid_7() -> None:
    """PID 7 → PerCarLapsMessage with 2 raw lap dicts preserved."""
    raw = load("pid_7_per_car_laps")
    msg = parse(raw)
    assert isinstance(msg, PerCarLapsMessage)
    assert msg.event_pid == 7
    assert msg.session == "R1"
    assert msg.starting_no == 7
    assert len(msg.laps) == 2
    assert msg.laps[0]["lap"] == 1


def test_dispatch_pid_501() -> None:
    """PID 501 → QualifyingMessage with 2-result table."""
    raw = load("pid_501_qualifying")
    msg = parse(raw)
    assert isinstance(msg, QualifyingMessage)
    assert msg.event_pid == 501
    assert len(msg.results) == 2
    assert msg.results[0].driver == "M. Müller"
    assert msg.results[0].best_lap_ms == 148200


def test_dispatch_pid_9002() -> None:
    """PID 9002 → StatisticsMessage with leading + best_sectors populated."""
    raw = load("pid_9002_statistics")
    msg = parse(raw)
    assert isinstance(msg, StatisticsMessage)
    assert msg.event_pid == 9002
    assert len(msg.leading) == 1
    assert len(msg.best_laps) == 1
    assert len(msg.best_sectors) == 1
    assert msg.best_sectors[0].sector == 1


def test_dispatch_time_sync() -> None:
    """``{type:'time', value:ms}`` → TimeSyncMessage with event_pid=-1 sentinel."""
    raw = load("time_sync")
    msg = parse(raw)
    assert isinstance(msg, TimeSyncMessage)
    assert msg.event_pid == -1
    assert msg.value_ms == 1700000000000


def test_dispatch_time_sync_does_not_enter_pid_branch() -> None:
    """The ``type:'time'`` branch matches BEFORE any eventPid lookup.

    A frame with both ``type:'time'`` and an ``eventPid`` that would
    otherwise match a known channel must still route to TimeSyncMessage
    — the server is allowed to send a time sync any time.
    """
    raw = {"type": "time", "value": 12345, "eventPid": 0}
    msg = parse(raw)
    assert isinstance(msg, TimeSyncMessage)
    assert msg.event_pid == -1
    assert msg.value_ms == 12345


def test_dispatch_unknown_pid() -> None:
    """Unknown eventPid → UnknownMessage(event_pid=9999), raw preserved."""
    raw = load("unknown_pid")
    msg = parse(raw)
    assert isinstance(msg, UnknownMessage)
    assert msg.event_pid == 9999
    # raw payload round-trip (PARSE-03)
    assert msg.raw["anything"] == 1
    assert msg.raw["futureServerField"] == "ignore-me"
