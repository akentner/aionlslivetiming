"""Freshness, Source, last_update_ms, and clear() transitions."""

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
from aionlslivetiming.state import Freshness, RaceState, Source


def _initial() -> InitialStateMessage:
    return InitialStateMessage(
        pid=1,
        ver="1.0",
        export_id="exp",
        track_name="Nordschleife",
        session=SessionInfo(session="R1"),
        results=(CarResult(starting_no=7, position=1, class_name="SP9", laps=10),),
    )


def test_freshness_starts_resync() -> None:
    """A fresh RaceState is RESYNCING until the first apply()."""
    state = RaceState()
    assert state.freshness == Freshness.RESYNCING


def test_freshness_becomes_fresh_after_apply() -> None:
    """After apply(), freshness == FRESH."""
    state = RaceState()
    state.apply(_initial())
    assert state.freshness == Freshness.FRESH


def test_freshness_resync_after_clear() -> None:
    """After clear(), freshness returns to RESYNCING."""
    state = RaceState()
    state.apply(_initial())
    assert state.freshness == Freshness.FRESH
    state.clear()
    assert state.freshness == Freshness.RESYNCING


def test_last_update_ms_set_after_apply() -> None:
    """last_update_ms is None until the first apply; set to wall-clock ms after."""
    state = RaceState()
    assert state.last_update_ms is None
    state.apply(_initial())
    assert state.last_update_ms is not None
    assert state.last_update_ms > 0


def test_source_default_live() -> None:
    """A new RaceState defaults to Source.LIVE."""
    state = RaceState()
    assert state.source == Source.LIVE


def test_set_source() -> None:
    """set_source() updates state.source; accepts all three values."""
    state = RaceState()
    state.set_source(Source.REPLAY)
    assert state.source == Source.REPLAY
    state.set_source(Source.IMPORTED)
    assert state.source == Source.IMPORTED
    state.set_source(Source.LIVE)
    assert state.source == Source.LIVE


def test_clear_empties_all_subcaches() -> None:
    """clear() empties every sub-cache and resets freshness to RESYNCING."""
    state = RaceState()
    state.apply(_initial())
    state.apply(TrackStateMessage(track_state="GREEN", time_state="RUNNING"))
    state.apply(RaceMessage(text="Pit", category="PIT", starting_no=7, session="R1"))
    state.apply(
        PerCarLapsMessage(
            session="R1",
            starting_no=7,
            laps=({"lap": 1, "time": 168200, "s1": 32150, "s2": 58720, "s3": 77330},),
        )
    )
    state.apply(
        QualifyingMessage(
            results=(CarResult(starting_no=7, position=1, best_lap_ms=148200),),
        )
    )
    state.apply(
        StatisticsMessage(
            leading=(CarResult(starting_no=7, position=1, best_lap_ms=162340),),
            best_sectors=(BestSector(starting_no=7, sector=1, value_ms=32000),),
        )
    )

    # Sanity: caches are populated
    assert state.cars
    assert state.messages
    assert state.laps(7)
    assert state.qualifying
    assert state.stats_leading
    assert state.stats_best_sectors

    state.clear()

    assert state.cars == {}
    assert state.track is None
    assert state.track_name is None
    assert state.messages == ()
    assert state.laps(7) == []
    assert state.qualifying == ()
    assert state.stats_leading == ()
    assert state.stats_best_laps == ()
    assert state.stats_best_sectors == {}
    assert state.last_update_ms is None
    assert state.freshness == Freshness.RESYNCING
