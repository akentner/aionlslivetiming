"""Per-class construction + frozen + raw round-trip tests for the 8 Messages.

Each test loads its fixture JSON (the public contract documented in
01-02 plan §D-08) and constructs the matching ``Message`` dataclass to
prove that the constructors accept the shape the parser will feed them.

Per PARSE-05 every Message is ``@dataclass(frozen=True, slots=True)``
with ``event_pid: ClassVar[int]`` and ``raw: Mapping[str, Any]``.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

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
from aionlslivetiming.events.common import BestSector, CarResult, SessionInfo, TimeOfDay

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "messages"


def load_fixture(name: str) -> dict[str, Any]:
    """Load and JSON-parse a fixture file by name (no .json suffix)."""
    return json.loads((FIXTURES / f"{name}.json").read_text())


# ---------------------------------------------------------------------------
# Per-class happy-path construction tests
# ---------------------------------------------------------------------------


def test_initial_state_construction() -> None:
    """PID 0 happy path: full results + best sectors + session info round-trip."""
    raw = load_fixture("pid_0_initial")
    msg = InitialStateMessage(
        pid=raw["PID"],
        ver=raw["VER"],
        export_id=raw["EXPORTID"],
        track_name=raw["TRACKNAME"],
        session=SessionInfo(
            session=raw["SESSION"],
            cup=raw["CUP"],
            heat=raw["HEAT"],
            heat_type=raw["HEATTYPE"],
        ),
        results=(
            CarResult(
                starting_no=7,
                position=1,
                class_name="SP9",
                driver="M. Müller",
                laps=28,
                total_time_ms=7200000,
                gap_to_leader_ms=0,
                best_lap_ms=162340,
            ),
            CarResult(
                starting_no=11,
                position=2,
                class_name="SP9",
                driver="F. Schmidt",
                laps=28,
                total_time_ms=7205421,
                gap_to_leader_ms=5421,
                best_lap_ms=162890,
            ),
        ),
        best_sectors=(
            BestSector(starting_no=7, sector=1, value_ms=32150, driver="M. Müller"),
            BestSector(starting_no=7, sector=2, value_ms=58720, driver="M. Müller"),
        ),
        raw=raw,
    )
    assert msg.event_pid == 0
    assert msg.track_name == "Nürburgring Nordschleife"
    assert msg.results[0].starting_no == 7
    assert msg.results[0].driver == "M. Müller"
    assert msg.results[1].position == 2
    assert msg.best_sectors[0].sector == 1
    assert msg.best_sectors[0].value_ms == 32150
    assert msg.lts_not_found is False
    # raw payload round-trip
    assert msg.raw["PID"] == 12345
    assert msg.raw["EXPORTID"] == "abc-123"


def test_lts_not_found_construction() -> None:
    """PID 0 LTS_NOT_FOUND path: lts_not_found flag survives."""
    raw = load_fixture("pid_0_lts_not_found")
    msg = InitialStateMessage(
        pid=raw["PID"],
        ver=raw["VER"],
        export_id=raw["EXPORTID"],
        track_name="",
        session=SessionInfo(session=""),
        lts_not_found=True,
        raw=raw,
    )
    assert msg.lts_not_found is True
    assert msg.results == ()
    assert msg.best_sectors == ()
    assert msg.raw["LTS_NOT_FOUND"] is True


def test_track_state_running_construction() -> None:
    """PID 4 running: TOD present, end_time None."""
    raw = load_fixture("pid_4_track_state_running")
    msg = TrackStateMessage(
        track_state=raw["TRACKSTATE"],
        time_state=raw["TIMESTATE"],
        tod=TimeOfDay(value_ms=raw["TOD"]["value"]),
        raw=raw,
    )
    assert msg.event_pid == 4
    assert msg.track_state == "GREEN"
    assert msg.time_state == "RUNNING"
    assert msg.tod is not None
    assert msg.tod.value_ms == 1834000
    assert msg.end_time is None
    assert msg.raw["TOD"]["value"] == 1834000


def test_track_state_finished_construction() -> None:
    """PID 4 chequered: ENDTIME present, tod may be None."""
    raw = load_fixture("pid_4_track_state_finished")
    msg = TrackStateMessage(
        track_state=raw["TRACKSTATE"],
        time_state=raw["TIMESTATE"],
        end_time=TimeOfDay(value_ms=raw["ENDTIME"]["value"]),
        raw=raw,
    )
    assert msg.track_state == "CHEQUERED"
    assert msg.time_state == "FINISHED"
    assert msg.end_time is not None
    assert msg.end_time.value_ms == 7200000
    assert msg.raw["ENDTIME"]["value"] == 7200000


def test_race_message_pit_construction() -> None:
    """PID 3 pit: starting_no + session are populated."""
    raw = load_fixture("pid_3_race_message_pit")
    msg = RaceMessage(
        text=raw["text"],
        category=raw["type"],
        starting_no=raw["startingNo"],
        session=raw["session"],
        raw=raw,
    )
    assert msg.event_pid == 3
    assert msg.category == "PIT"
    assert msg.text == "Car #7 in pits"
    assert msg.starting_no == 7
    assert msg.session == "R1"
    assert msg.raw["startingNo"] == 7


def test_race_message_flag_construction() -> None:
    """PID 3 flag: starting_no + session are None (sector-level, not car-level)."""
    raw = load_fixture("pid_3_race_message_flag")
    msg = RaceMessage(
        text=raw["text"],
        category=raw["type"],
        raw=raw,
    )
    assert msg.event_pid == 3
    assert msg.category == "FLAG"
    assert msg.starting_no is None
    assert msg.session is None
    assert msg.raw["sector"] == 3


def test_per_car_laps_construction() -> None:
    """PID 7: laps tuple preserves raw lap dicts verbatim (Phase 2 parses them)."""
    raw = load_fixture("pid_7_per_car_laps")
    msg = PerCarLapsMessage(
        session=raw["session"],
        starting_no=raw["startingNo"],
        laps=tuple(raw["laps"]),
        raw=raw,
    )
    assert msg.event_pid == 7
    assert msg.session == "R1"
    assert msg.starting_no == 7
    assert len(msg.laps) == 2
    assert msg.laps[0]["lap"] == 1
    assert msg.laps[0]["time"] == 168200
    assert msg.laps[1]["lap"] == 2
    # raw preserved
    assert msg.raw["startingNo"] == 7


def test_qualifying_construction() -> None:
    """PID 501: results tuple carries qualifying rows."""
    raw = load_fixture("pid_501_qualifying")
    msg = QualifyingMessage(
        results=tuple(
            CarResult(
                starting_no=row["startingNo"],
                position=row["position"],
                class_name=row["class"],
                driver=row["driver"],
                best_lap_ms=row["best"],
            )
            for row in raw["RESULT"]
        ),
        raw=raw,
    )
    assert msg.event_pid == 501
    assert len(msg.results) == 2
    assert msg.results[0].starting_no == 7
    assert msg.results[0].best_lap_ms == 148200
    assert msg.results[1].position == 2


def test_statistics_construction() -> None:
    """PID 9002: leading + best_laps + best_sectors all populated."""
    raw = load_fixture("pid_9002_statistics")
    msg = StatisticsMessage(
        leading=tuple(
            CarResult(
                starting_no=row["startingNo"],
                position=row["position"],
                class_name=row["class"],
                driver=row["driver"],
                laps=row["laps"],
                best_lap_ms=row["best"],
            )
            for row in raw["LEADING"]
        ),
        best_laps=tuple(
            CarResult(
                starting_no=row["startingNo"],
                position=row["position"],
                class_name=row["class"],
                driver=row["driver"],
                laps=row["laps"],
                best_lap_ms=row["best"],
            )
            for row in raw["BEST_LAPS"]
        ),
        best_sectors=tuple(
            BestSector(
                starting_no=row["startingNo"],
                sector=row["sector"],
                value_ms=row["value"],
                driver=row.get("driver"),
            )
            for row in raw["BEST_SECTORS"]
        ),
        raw=raw,
    )
    assert msg.event_pid == 9002
    assert len(msg.leading) == 1
    assert msg.leading[0].starting_no == 7
    assert len(msg.best_laps) == 1
    assert len(msg.best_sectors) == 1
    assert msg.best_sectors[0].sector == 1
    assert msg.best_sectors[0].value_ms == 31800


def test_time_sync_construction() -> None:
    """``type:'time'`` frame → TimeSyncMessage with event_pid=-1 sentinel."""
    raw = load_fixture("time_sync")
    msg = TimeSyncMessage(value_ms=raw["value"], raw=raw)
    assert msg.event_pid == -1
    assert msg.value_ms == 1700000000000
    assert msg.raw["type"] == "time"


def test_unknown_construction() -> None:
    """UnknownMessage carries the actual (unknown) PID as an instance field."""
    raw = load_fixture("unknown_pid")
    msg = UnknownMessage(event_pid=raw["eventPid"], raw=raw)
    assert msg.event_pid == 9999
    # raw payload preserved
    assert msg.raw["anything"] == 1
    assert msg.raw["futureServerField"] == "ignore-me"


# ---------------------------------------------------------------------------
# Frozen enforcement (PARSE-05) — sweep all 8 classes
# ---------------------------------------------------------------------------


def test_frozen_enforcement() -> None:
    """All 8 Message dataclasses reject post-construction field assignment."""
    cases = [
        InitialStateMessage(
            pid=1,
            ver="1",
            export_id="x",
            track_name="t",
            session=SessionInfo(session="R1"),
        ),
        TrackStateMessage(track_state="GREEN", time_state="RUNNING"),
        RaceMessage(text="x", category="INFO"),
        PerCarLapsMessage(session="R1", starting_no=7),
        QualifyingMessage(),
        StatisticsMessage(),
        TimeSyncMessage(value_ms=0),
        UnknownMessage(event_pid=9999),
    ]
    assert len(cases) == 8, "expected exactly 8 Message dataclasses"
    for msg in cases:
        with pytest.raises(dataclasses.FrozenInstanceError):
            msg.raw = {}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# raw payload round-trip (PARSE-03) — unknown server fields preserved
# ---------------------------------------------------------------------------


def test_raw_preserves_unknown_fields() -> None:
    """Unknown server fields in raw survive the constructor."""
    raw = {
        "PID": 1,
        "VER": "1.0",
        "EXPORTID": "x",
        "TRACKNAME": "t",
        "SESSION": "R1",
        "futureServerField": "data",
        "anotherNewField": 42,
    }
    msg = InitialStateMessage(
        pid=raw["PID"],
        ver=raw["VER"],
        export_id=raw["EXPORTID"],
        track_name=raw["TRACKNAME"],
        session=SessionInfo(session=raw["SESSION"]),
        raw=raw,
    )
    assert isinstance(msg.raw, Mapping)
    assert msg.raw["futureServerField"] == "data"
    assert msg.raw["anotherNewField"] == 42


def test_event_pid_classvars_are_distinct_per_class() -> None:
    """Each Message class has the correct event_pid ClassVar.

    TimeSyncMessage is the sentinel -1 (no real PID); the others map to
    the NLS server's documented channel ids.
    """
    assert InitialStateMessage.event_pid == 0
    assert RaceMessage.event_pid == 3
    assert TrackStateMessage.event_pid == 4
    assert PerCarLapsMessage.event_pid == 7
    assert QualifyingMessage.event_pid == 501
    assert StatisticsMessage.event_pid == 9002
    assert TimeSyncMessage.event_pid == -1
