"""Per-message-type apply() coverage for RaceState.

Each test constructs typed Message objects directly (no parser, no
fixtures, no I/O) and feeds them into a fresh ``RaceState()``. The
boundary rule from ARCHITECTURE.md line 166 is: state/ imports only
from events/, never from parser/ or transport/.
"""

from __future__ import annotations

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
from aionlslivetiming.events.common import BestSector, CarResult, SessionInfo, TimeOfDay
from aionlslivetiming.state import RaceState


def _initial_msg(results: tuple[CarResult, ...] = ()) -> InitialStateMessage:
    return InitialStateMessage(
        pid=1,
        ver="1.0",
        export_id="exp-1",
        track_name="Nürburgring Nordschleife",
        session=SessionInfo(session="R1", cup="NLS", heat="H1", heat_type="RACE"),
        results=results,
    )


def _r1_initial() -> InitialStateMessage:
    return _initial_msg(
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
        )
    )


# ---------------------------------------------------------------------------
# Initial-state (PID 0)
# ---------------------------------------------------------------------------


def test_apply_initial_state_populates_cars_and_metadata() -> None:
    """PID 0 populates cars, track_name, ver, export_id."""
    state = RaceState()
    state.apply(_r1_initial())

    assert state.track_name == "Nürburgring Nordschleife"
    assert state.ver == "1.0"
    assert state.export_id == "exp-1"
    assert set(state.cars.keys()) == {7, 11}
    assert state.cars[7].position == 1
    assert state.cars[7].class_name == "SP9"
    assert state.cars[7].driver == "M. Müller"
    assert state.cars[7].laps_completed == 28
    assert state.cars[7].best_lap_ms == 162340
    assert state.cars[11].position == 2
    assert state.cars[11].gap_to_leader_ms == 5421
    # Standings ordered by position (None last)
    assert [c.starting_no for c in state.standings()] == [7, 11]


def test_apply_initial_state_resets_previous_cars() -> None:
    """Two InitialStateMessage in sequence: cars dict matches only the second.

    PID 0 is a full reset per ARCHITECTURE.md.
    """
    state = RaceState()
    state.apply(_r1_initial())

    second = _initial_msg(
        results=(
            CarResult(starting_no=99, position=1, class_name="TCR"),
        )
    )
    state.apply(second)

    assert set(state.cars.keys()) == {99}
    assert state.cars[99].class_name == "TCR"


# ---------------------------------------------------------------------------
# Track-state (PID 4)
# ---------------------------------------------------------------------------


def test_apply_track_state_replaces_track() -> None:
    """PID 4 updates state.track; second PID 4 replaces it."""
    state = RaceState()
    state.apply(
        TrackStateMessage(
            track_state="GREEN",
            time_state="RUNNING",
            tod=TimeOfDay(value_ms=5000),
        )
    )
    assert state.track is not None
    assert state.track.track_state == "GREEN"
    assert state.track.time_state == "RUNNING"
    assert state.track.tod_ms == 5000

    state.apply(
        TrackStateMessage(
            track_state="YELLOW",
            time_state="RUNNING",
            tod=TimeOfDay(value_ms=7500),
        )
    )
    assert state.track is not None
    assert state.track.track_state == "YELLOW"
    assert state.track.tod_ms == 7500


def test_apply_track_state_with_end_time() -> None:
    """PID 4 finished: end_time_ms survives the flatten."""
    state = RaceState()
    state.apply(
        TrackStateMessage(
            track_state="CHEQUERED",
            time_state="FINISHED",
            end_time=TimeOfDay(value_ms=7200000),
        )
    )
    assert state.track is not None
    assert state.track.end_time_ms == 7200000
    assert state.track.tod_ms is None


# ---------------------------------------------------------------------------
# Race-message (PID 3)
# ---------------------------------------------------------------------------


def test_apply_race_message_appends() -> None:
    """PID 3 pit: appends to state.messages with all fields."""
    state = RaceState()
    state.apply(
        RaceMessage(
            text="Car #7 in pits",
            category="PIT",
            starting_no=7,
            session="R1",
        )
    )
    assert len(state.messages) == 1
    assert state.messages[0].text == "Car #7 in pits"
    assert state.messages[0].category == "PIT"
    assert state.messages[0].starting_no == 7


def test_apply_race_message_without_starting_no() -> None:
    """PID 3 sector-level flag: starting_no/session may be None."""
    state = RaceState()
    state.apply(
        RaceMessage(text="Yellow flag sector 1", category="FLAG"),
    )
    assert len(state.messages) == 1
    assert state.messages[0].starting_no is None
    assert state.messages[0].session is None


# ---------------------------------------------------------------------------
# Per-car laps (PID 7)
# ---------------------------------------------------------------------------


def test_apply_per_car_laps_extracts_lap_records() -> None:
    """PID 7 builds LapRecord list keyed by (session, starting_no, lap_no)."""
    state = RaceState()
    state.apply(
        PerCarLapsMessage(
            session="R1",
            starting_no=7,
            laps=(
                {"lap": 1, "time": 168200, "s1": 32150, "s2": 58720, "s3": 77330},
                {"lap": 2, "time": 167100, "s1": 32000, "s2": 58500, "s3": 76600},
            ),
        )
    )
    laps = state.laps(7)
    assert len(laps) == 2
    assert laps[0].lap_no == 1
    assert laps[0].time_ms == 168200
    assert laps[0].s1_ms == 32150
    assert laps[0].s2_ms == 58720
    assert laps[0].s3_ms == 77330
    assert laps[1].lap_no == 2
    assert laps[1].time_ms == 167100


def test_apply_per_car_laps_drops_malformed_lap() -> None:
    """D-03: malformed lap dicts are dropped, never crash."""
    state = RaceState()
    state.apply(
        PerCarLapsMessage(
            session="R1",
            starting_no=7,
            laps=(
                {"lap": 1, "time": "not-a-number"},
                {"lap": 2},  # missing time
            ),
        )
    )
    assert state.laps(7) == []


# ---------------------------------------------------------------------------
# Qualifying (PID 501)
# ---------------------------------------------------------------------------


def test_apply_qualifying_replaces_results() -> None:
    """PID 501 results tuple replaces previous qualifying on every apply."""
    state = RaceState()
    state.apply(
        QualifyingMessage(
            results=(
                CarResult(starting_no=7, position=1, best_lap_ms=148200),
                CarResult(starting_no=11, position=2, best_lap_ms=148900),
                CarResult(starting_no=12, position=3, best_lap_ms=149100),
            ),
        )
    )
    assert len(state.qualifying) == 3

    state.apply(
        QualifyingMessage(
            results=(CarResult(starting_no=7, position=1, best_lap_ms=147900),),
        )
    )
    assert len(state.qualifying) == 1
    assert state.qualifying[0].best_lap_ms == 147900


# ---------------------------------------------------------------------------
# Statistics (PID 9002)
# ---------------------------------------------------------------------------


def test_apply_statistics_replaces_leading_best_laps() -> None:
    """PID 9002 leading + best_laps replace on every apply."""
    state = RaceState()
    state.apply(
        StatisticsMessage(
            leading=(CarResult(starting_no=7, position=1, best_lap_ms=162340),),
            best_laps=(CarResult(starting_no=7, position=1, best_lap_ms=162340),),
        )
    )
    assert len(state.stats_leading) == 1
    assert len(state.stats_best_laps) == 1

    state.apply(
        StatisticsMessage(
            leading=(CarResult(starting_no=11, position=1, best_lap_ms=162100),),
            best_laps=(CarResult(starting_no=11, position=1, best_lap_ms=162100),),
        )
    )
    assert state.stats_leading[0].starting_no == 11
    assert state.stats_best_laps[0].starting_no == 11


def test_apply_statistics_sector_bests_keep_min() -> None:
    """sector_bests[(starting_no, sector)] keeps the minimum value_ms."""
    state = RaceState()
    state.apply(
        StatisticsMessage(
            best_sectors=(BestSector(starting_no=7, sector=1, value_ms=32000),),
        )
    )
    assert state.stats_best_sectors[(7, 1)] == 32000

    state.apply(
        StatisticsMessage(
            best_sectors=(BestSector(starting_no=7, sector=1, value_ms=31000),),
        )
    )
    assert state.stats_best_sectors[(7, 1)] == 31000

    # Worse sector time must not overwrite the best
    state.apply(
        StatisticsMessage(
            best_sectors=(BestSector(starting_no=7, sector=1, value_ms=32500),),
        )
    )
    assert state.stats_best_sectors[(7, 1)] == 31000


# ---------------------------------------------------------------------------
# No-op messages
# ---------------------------------------------------------------------------


def test_apply_time_sync_is_noop() -> None:
    """TimeSyncMessage is a heartbeat — must not mutate state."""
    state = RaceState()
    state.apply(TimeSyncMessage(value_ms=12345))
    assert state.cars == {}
    assert state.messages == ()
    assert state.laps(7) == []


def test_apply_unknown_is_noop() -> None:
    """UnknownMessage is forward-compat — must not mutate state."""
    state = RaceState()
    state.apply(UnknownMessage(event_pid=9999, raw={"anything": 1}))
    assert state.cars == {}
    assert state.messages == ()
    assert state.track is None


# ---------------------------------------------------------------------------
# Helper used by idempotency suite
# ---------------------------------------------------------------------------


def state_to_dict(state: RaceState) -> dict[str, Any]:
    """Snapshot the structural shape of a RaceState for equality checks."""
    return {
        "cars": {no: c.model_dump() for no, c in state.cars.items()},
        "track": state.track.model_dump() if state.track else None,
        "track_name": state.track_name,
        "messages": [m.text for m in state.messages],
        "qualifying": [r.model_dump() if hasattr(r, "model_dump") else r for r in state.qualifying],
        "stats_leading": [
            r.model_dump() if hasattr(r, "model_dump") else r for r in state.stats_leading
        ],
        "stats_best_sectors": dict(state.stats_best_sectors),
    }
