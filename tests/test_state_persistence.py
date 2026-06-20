"""JSON snapshot round-trip persistence tests for RaceState (STATE-06, STATE-07).

STATE-06: state.to_json() exports the full cache to a JSON string.
STATE-07: RaceState.from_json(s) / state.import_json(s) reconstructs / replaces
the cache; structurally equivalent to the original after round-trip.

The persistence path is user-initiated (export / import), not on the WS
hot path, so stdlib json is sufficient and orjson stays optional.
"""

from __future__ import annotations

import json

import pytest

from aionlslivetiming import RaceState
from aionlslivetiming.events import (
    CarResult,
    InitialStateMessage,
    PerCarLapsMessage,
    QualifyingMessage,
    RaceMessage,
    SessionInfo,
    StatisticsMessage,
    TimeOfDay,
    TrackStateMessage,
)
from aionlslivetiming.events.common import BestSector
from aionlslivetiming.state.enums import Freshness, Source


def make_full_state() -> RaceState:
    """Build a fully-populated RaceState (every message type applied)."""
    s = RaceState()
    s.apply(
        InitialStateMessage(
            pid=1,
            ver="54",
            export_id="abc-123",
            track_name="Nordschleife",
            session=SessionInfo(session="R1", heat="1", heat_type="R", cup="NLS"),
            results=(
                CarResult(
                    starting_no=7,
                    position=1,
                    class_name="SP9",
                    driver="M. Mueller",
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
                BestSector(starting_no=7, sector=1, value_ms=32150, driver="M. Mueller"),
                BestSector(starting_no=7, sector=2, value_ms=58720, driver="M. Mueller"),
            ),
        )
    )
    s.apply(
        TrackStateMessage(
            track_state="GREEN",
            time_state="RUNNING",
            tod=TimeOfDay(value_ms=1234567),
        )
    )
    s.apply(RaceMessage(text="Car 7 pit in", category="PIT", starting_no=7, session="R1"))
    s.apply(
        PerCarLapsMessage(
            session="R1",
            starting_no=7,
            laps=(
                {"lap": 1, "time": 168200, "s1": 32150, "s2": 58720, "s3": 77330},
                {"lap": 2, "time": 162340, "s1": 31000, "s2": 55000, "s3": 76340},
            ),
        )
    )
    s.apply(
        QualifyingMessage(
            results=(CarResult(starting_no=7, position=1, class_name="SP9", best_lap_ms=162340),)
        )
    )
    s.apply(
        StatisticsMessage(
            leading=(CarResult(starting_no=7, position=1, best_lap_ms=162340),)
        )
    )
    return s


def test_round_trip_preserves_everything():
    s1 = make_full_state()
    s1.set_source(Source.REPLAY)
    snapshot = s1.to_json()

    payload = json.loads(snapshot)
    assert payload["schema_version"] == 1
    assert payload["source"] == "REPLAY"

    s2 = RaceState.from_json(snapshot)
    assert s2.source == Source.REPLAY
    assert s2.freshness == Freshness.FRESH
    assert s2.last_update_ms == s1.last_update_ms
    assert s2.track_name == "Nordschleife"
    assert s2.ver == "54"
    assert s2.export_id == "abc-123"
    assert s2.session.session == "R1"
    assert s2.session.cup == "NLS"
    assert s2.track.track_state == "GREEN"
    assert s2.track.tod_ms == 1234567
    assert sorted(s2.cars.keys()) == [7, 11]
    assert s2.cars[7].position == 1
    assert s2.cars[7].best_lap_ms == 162340
    assert s2.cars[7].class_name == "SP9"
    assert s2.cars[11].position == 2
    assert len(s2.messages) == 1
    assert s2.messages[0].text == "Car 7 pit in"
    assert s2.messages[0].starting_no == 7
    laps = s2.laps(7)
    assert len(laps) == 2
    assert laps[0].lap_no == 1
    assert laps[0].time_ms == 168200
    assert laps[1].time_ms == 162340
    assert len(s2.qualifying) == 1
    assert s2.qualifying[0].starting_no == 7
    assert len(s2.stats_leading) == 1


def test_round_trip_empty_state():
    s1 = RaceState()
    snapshot = s1.to_json()
    s2 = RaceState.from_json(snapshot)
    assert s2.cars == {}
    assert s2.messages == ()
    assert s2.qualifying == ()
    assert s2.stats_leading == ()
    assert s2.track is None
    assert s2.source == Source.LIVE


def test_round_trip_preserves_idempotency_keys():
    """After round-trip, re-applying the same RaceMessage does NOT duplicate it."""
    s1 = RaceState()
    msg = RaceMessage(text="Car 7 pit in", category="PIT", starting_no=7)
    s1.apply(msg)
    s1.apply(msg)
    assert len(s1.messages) == 1
    snapshot = s1.to_json()
    s2 = RaceState.from_json(snapshot)
    s2.apply(msg)
    assert len(s2.messages) == 1


def test_import_json_replaces_state():
    s1 = make_full_state()
    snapshot = s1.to_json()
    s2 = RaceState()
    s2.apply(
        InitialStateMessage(
            pid=99,
            ver="99",
            export_id="other",
            track_name="Spa",
            session=SessionInfo(session="R2"),
            results=(CarResult(starting_no=99, position=1),),
        )
    )
    s2.import_json(snapshot)
    assert s2.track_name == "Nordschleife"
    assert s2.cars[7].position == 1
    assert s2.export_id == "abc-123"


def test_invalid_json_raises_value_error():
    with pytest.raises(ValueError, match="invalid state JSON"):
        RaceState.from_json("{not valid json")


def test_missing_schema_version_raises():
    with pytest.raises(ValueError, match="unsupported schema_version"):
        RaceState.from_json('{"cars": {}}')


def test_unsupported_schema_version_raises():
    with pytest.raises(ValueError, match="unsupported schema_version"):
        RaceState.from_json('{"schema_version": 999}')


def test_top_level_not_object_raises():
    with pytest.raises(ValueError, match="expected an object"):
        RaceState.from_json("[]")


def test_snapshot_is_valid_json_string():
    s = make_full_state()
    snapshot = s.to_json()
    assert isinstance(snapshot, str)
    parsed = json.loads(snapshot)
    assert isinstance(parsed, dict)


def test_filter_after_round_trip():
    """Filter must work on a freshly-imported state."""
    s1 = make_full_state()
    snapshot = s1.to_json()
    s2 = RaceState.from_json(snapshot)
    sp9_cars = s2.filter().by_class("SP9").cars()
    assert len(sp9_cars) == 2
    assert {c.starting_no for c in sp9_cars} == {7, 11}