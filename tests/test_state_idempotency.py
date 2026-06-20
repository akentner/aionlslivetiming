"""Apply-the-same-message-twice must yield structurally equal state.

Idempotency is required for the convergence semantics: the server can
replay or duplicate messages during high-frequency updates and the
state cache must not double-count.
"""

from __future__ import annotations

from aionlslivetiming.events import (
    InitialStateMessage,
    PerCarLapsMessage,
    QualifyingMessage,
    RaceMessage,
    StatisticsMessage,
    TrackStateMessage,
)
from aionlslivetiming.events.common import BestSector, CarResult, SessionInfo, TimeOfDay
from aionlslivetiming.state import RaceState
from aionlslivetiming.state.lap import LapRecord
from tests.test_state_apply import state_to_dict


def _initial() -> InitialStateMessage:
    return InitialStateMessage(
        pid=1,
        ver="1.0",
        export_id="exp",
        track_name="Nordschleife",
        session=SessionInfo(session="R1"),
        results=(
            CarResult(
                starting_no=7,
                position=1,
                class_name="SP9",
                driver="M",
                laps=10,
                best_lap_ms=162340,
            ),
        ),
    )


def test_idempotent_initial_state() -> None:
    """Two InitialStateMessage apply → cars dict equal to a single apply."""
    a = RaceState()
    a.apply(_initial())
    b = RaceState()
    b.apply(_initial())
    b.apply(_initial())
    assert a.cars == b.cars


def test_idempotent_track_state() -> None:
    """Two TrackStateMessage apply → track values equal (new instance OK)."""
    msg = TrackStateMessage(
        track_state="GREEN",
        time_state="RUNNING",
        tod=TimeOfDay(value_ms=5000),
    )
    a = RaceState()
    a.apply(msg)
    b = RaceState()
    b.apply(msg)
    b.apply(msg)
    assert a.track is not None
    assert b.track is not None
    assert a.track.model_dump() == b.track.model_dump()


def test_idempotent_race_message_dedupes() -> None:
    """Two identical RaceMessage → state.messages has length 1."""
    state = RaceState()
    msg = RaceMessage(text="Car #7 in pits", category="PIT", starting_no=7, session="R1")
    state.apply(msg)
    state.apply(msg)
    assert len(state.messages) == 1


def test_idempotent_per_car_laps() -> None:
    """Two identical PerCarLapsMessage → state.laps(no) has same length + values."""
    msg = PerCarLapsMessage(
        session="R1",
        starting_no=7,
        laps=(
            {"lap": 1, "time": 168200, "s1": 32150, "s2": 58720, "s3": 77330},
            {"lap": 2, "time": 167100, "s1": 32000, "s2": 58500, "s3": 76600},
        ),
    )
    a = RaceState()
    a.apply(msg)
    b = RaceState()
    b.apply(msg)
    b.apply(msg)
    assert a.laps(7) == b.laps(7)
    assert len(b.laps(7)) == 2
    assert all(isinstance(lr, LapRecord) for lr in b.laps(7))


def test_idempotent_qualifying() -> None:
    """Two identical QualifyingMessage → state.qualifying structurally equal."""
    msg = QualifyingMessage(
        results=(CarResult(starting_no=7, position=1, best_lap_ms=148200),),
    )
    a = RaceState()
    a.apply(msg)
    b = RaceState()
    b.apply(msg)
    b.apply(msg)
    assert a.qualifying == b.qualifying
    assert len(b.qualifying) == 1


def test_idempotent_statistics() -> None:
    """Two identical StatisticsMessage → all three sub-tables structurally equal."""
    msg = StatisticsMessage(
        leading=(CarResult(starting_no=7, position=1, best_lap_ms=162340),),
        best_laps=(CarResult(starting_no=7, position=1, best_lap_ms=162340),),
        best_sectors=(BestSector(starting_no=7, sector=1, value_ms=32000),),
    )
    a = RaceState()
    a.apply(msg)
    b = RaceState()
    b.apply(msg)
    b.apply(msg)
    assert a.stats_leading == b.stats_leading
    assert a.stats_best_laps == b.stats_best_laps
    assert a.stats_best_sectors == b.stats_best_sectors


def test_full_pipeline_idempotent() -> None:
    """A full message sequence, applied twice, yields a structurally equal snapshot."""
    sequence: list[object] = [
        _initial(),
        TrackStateMessage(
            track_state="GREEN",
            time_state="RUNNING",
            tod=TimeOfDay(value_ms=5000),
        ),
        RaceMessage(text="Pit", category="PIT", starting_no=7, session="R1"),
        PerCarLapsMessage(
            session="R1",
            starting_no=7,
            laps=({"lap": 1, "time": 168200, "s1": 32150, "s2": 58720, "s3": 77330},),
        ),
        QualifyingMessage(
            results=(CarResult(starting_no=7, position=1, best_lap_ms=148200),),
        ),
        StatisticsMessage(
            leading=(CarResult(starting_no=7, position=1, best_lap_ms=162340),),
            best_sectors=(BestSector(starting_no=7, sector=1, value_ms=32000),),
        ),
    ]
    a = RaceState()
    for m in sequence:
        a.apply(m)
    snap = state_to_dict(a)

    b = RaceState()
    for m in sequence:
        b.apply(m)
    for m in sequence:
        b.apply(m)
    assert state_to_dict(b) == snap
