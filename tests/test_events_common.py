"""Tests for the shared value types in :mod:`aionlslivetiming.events.common`.

These dataclasses (``TimeOfDay``, ``SessionInfo``, ``BestSector``,
``CarResult``) are the embedded leaf types the 8 Message classes compose.
They are exercised here in isolation so a parser bug does not mask a
type bug and vice versa.

Per D-01 all are ``@dataclass(frozen=True, slots=True)``.
Per D-03 every optional field defaults so the parser never crashes on
missing server fields.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from aionlslivetiming.events.common import BestSector, CarResult, SessionInfo, TimeOfDay


def test_time_of_day() -> None:
    """TimeOfDay stores a single integer ms value and is frozen."""
    tod = TimeOfDay(value_ms=1834000)
    assert tod.value_ms == 1834000
    with pytest.raises(FrozenInstanceError):
        tod.value_ms = 1  # type: ignore[misc]


def test_session_info() -> None:
    """SessionInfo requires ``session``; all other fields default to None."""
    info = SessionInfo(session="R1")
    assert info.session == "R1"
    assert info.starting_no is None
    assert info.heat is None
    assert info.heat_type is None
    assert info.cup is None
    assert info.event_id is None

    info_full = SessionInfo(
        session="Q",
        starting_no=7,
        heat="1",
        heat_type="R",
        cup="NLS",
        event_id="abc-123",
    )
    assert info_full.session == "Q"
    assert info_full.starting_no == 7
    assert info_full.heat == "1"
    assert info_full.heat_type == "R"
    assert info_full.cup == "NLS"
    assert info_full.event_id == "abc-123"


def test_session_info_frozen() -> None:
    """SessionInfo rejects post-construction assignment (frozen)."""
    info = SessionInfo(session="R1")
    with pytest.raises(FrozenInstanceError):
        info.session = "R2"  # type: ignore[misc]


def test_best_sector() -> None:
    """BestSector required fields are positional; driver defaults to None."""
    bs = BestSector(starting_no=7, sector=1, value_ms=32150)
    assert bs.starting_no == 7
    assert bs.sector == 1
    assert bs.value_ms == 32150
    assert bs.driver is None

    bs2 = BestSector(starting_no=11, sector=2, value_ms=58000, driver="F. Schmidt")
    assert bs2.driver == "F. Schmidt"


def test_best_sector_frozen() -> None:
    """BestSector rejects post-construction assignment (frozen)."""
    bs = BestSector(starting_no=7, sector=1, value_ms=32150)
    with pytest.raises(FrozenInstanceError):
        bs.value_ms = 0  # type: ignore[misc]


def test_car_result_required() -> None:
    """CarResult requires starting_no + position; optional fields default."""
    cr = CarResult(starting_no=7, position=1)
    assert cr.starting_no == 7
    assert cr.position == 1
    assert cr.class_name is None
    assert cr.driver is None
    assert cr.laps == 0
    assert cr.total_time_ms is None
    assert cr.gap_to_leader_ms is None
    assert cr.best_lap_ms is None


def test_car_result_full() -> None:
    """CarResult accepts the full per-row shape the server emits."""
    cr = CarResult(
        starting_no=7,
        position=1,
        class_name="SP9",
        driver="M. Müller",
        laps=28,
        total_time_ms=7200000,
        gap_to_leader_ms=0,
        best_lap_ms=162340,
    )
    assert cr.class_name == "SP9"
    assert cr.driver == "M. Müller"
    assert cr.laps == 28
    assert cr.total_time_ms == 7200000
    assert cr.gap_to_leader_ms == 0
    assert cr.best_lap_ms == 162340


def test_car_result_frozen() -> None:
    """CarResult rejects post-construction assignment (frozen)."""
    cr = CarResult(starting_no=7, position=1)
    with pytest.raises(FrozenInstanceError):
        cr.laps = 5  # type: ignore[misc]
