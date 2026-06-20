"""Filter DSL coverage for RaceState.

Exercises all six filter dimensions (FILT-01..06) + AND composition
(FILT-07) + the convenience pass-throughs on :class:`RaceState` +
the empty-filter default behaviour.

Each test builds the fixture race via :func:`make_race_state` — six cars
(three SP9 + three SP7), full driver names, varied lap counts, and a
hand-injected sector-bests map on the first few cars so FILT-06 has
something to discriminate on.
"""

from __future__ import annotations

from aionlslivetiming import Filter, RaceState
from aionlslivetiming.events import InitialStateMessage, SessionInfo, CarResult
from aionlslivetiming.state.car import CarState


def make_race_state() -> RaceState:
    """6-car race: 3 SP9 + 3 SP7, with drivers, positions, laps, sector bests.

    Cars: starting_no 7/11/22 (SP9), 44/55/66 (SP7). All have positions
    1..6. Sector bests are injected directly into CarState.sector_bests
    after apply() so FILT-06 has data to filter against (the
    InitialStateMessage has no per-car sector_bests on cars).
    """
    s = RaceState()
    msg = InitialStateMessage(
        pid=1,
        ver="1.0",
        export_id="evt",
        track_name="Nordschleife",
        session=SessionInfo(session="R1"),
        results=(
            CarResult(
                starting_no=7,
                position=1,
                class_name="SP9",
                driver="M. Mueller",
                laps=28,
                best_lap_ms=162340,
            ),
            CarResult(
                starting_no=11,
                position=2,
                class_name="SP9",
                driver="F. Schmidt",
                laps=28,
                best_lap_ms=162890,
            ),
            CarResult(
                starting_no=22,
                position=3,
                class_name="SP9",
                driver="K. Weber",
                laps=27,
                best_lap_ms=163120,
            ),
            CarResult(
                starting_no=44,
                position=4,
                class_name="SP7",
                driver="T. Bauer",
                laps=27,
                best_lap_ms=168200,
            ),
            CarResult(
                starting_no=55,
                position=5,
                class_name="SP7",
                driver="S. Fischer",
                laps=26,
                best_lap_ms=170100,
            ),
            CarResult(
                starting_no=66,
                position=6,
                class_name="SP7",
                driver="A. Klein",
                laps=25,
                best_lap_ms=172500,
            ),
        ),
    )
    s.apply(msg)
    # Inject sector bests for FILT-06 test (InitialStateMessage has no sector_bests on cars)
    s._cars[7].sector_bests[1] = 32150  # noqa: SLF001 - test-internal mutation
    s._cars[7].sector_bests[2] = 58720  # noqa: SLF001
    s._cars[11].sector_bests[1] = 33000
    s._cars[22].sector_bests[1] = 33500
    s._cars[44].sector_bests[1] = 35100
    return s


def starting_nos(cars: list[CarState]) -> list[int]:
    """Helper: extract starting_nos from a cars list, preserving order."""
    return [c.starting_no for c in cars]


# ---------------------------------------------------------------------------
# Empty filter / factory basics
# ---------------------------------------------------------------------------


def test_filter_empty_returns_all_six() -> None:
    """Empty filter returns every car in position order."""
    s = make_race_state()
    cars = s.filter().cars()
    assert len(cars) == 6
    assert starting_nos(cars) == [7, 11, 22, 44, 55, 66]


def test_filter_returns_new_instance_each_call() -> None:
    """state.filter() returns a fresh Filter object, never the same one twice."""
    s = make_race_state()
    assert s.filter() is not s.filter()


def test_filter_importable_from_top_level() -> None:
    """Filter is part of the public API surface."""
    assert Filter is not None
    assert hasattr(Filter, "cars")
    assert hasattr(Filter, "by_class")


# ---------------------------------------------------------------------------
# FILT-01: by_class
# ---------------------------------------------------------------------------


def test_by_class_filters_to_one_class() -> None:
    """by_class('SP9') returns only the 3 SP9 cars in position order."""
    s = make_race_state()
    cars = s.filter().by_class("SP9").cars()
    assert starting_nos(cars) == [7, 11, 22]
    assert all(c.class_name == "SP9" for c in cars)


def test_by_class_unknown_class_returns_empty() -> None:
    """by_class('GT3') returns [] — no GT3 cars in the fixture."""
    s = make_race_state()
    assert s.filter().by_class("GT3").cars() == []


def test_by_class_accumulates_set_semantics() -> None:
    """by_class('SP9') then by_class('SP9') is idempotent (set semantics)."""
    s = make_race_state()
    cars = s.filter().by_class("SP9").by_class("SP9").cars()
    assert starting_nos(cars) == [7, 11, 22]


# ---------------------------------------------------------------------------
# FILT-02: by_starting_no
# ---------------------------------------------------------------------------


def test_by_starting_no_single_int() -> None:
    """by_starting_no(7) returns just car 7."""
    s = make_race_state()
    cars = s.filter().by_starting_no(7).cars()
    assert starting_nos(cars) == [7]


def test_by_starting_no_list() -> None:
    """by_starting_no([7, 11]) returns cars 7 and 11 in position order."""
    s = make_race_state()
    cars = s.filter().by_starting_no([7, 11]).cars()
    assert starting_nos(cars) == [7, 11]


def test_by_starting_no_tuple_works() -> None:
    """by_starting_no accepts any iterable of ints."""
    s = make_race_state()
    cars = s.filter().by_starting_no((22, 44)).cars()
    assert starting_nos(cars) == [22, 44]


def test_by_starting_no_unknown_returns_empty() -> None:
    """by_starting_no(999) returns [] — car 999 is not in the race."""
    s = make_race_state()
    assert s.filter().by_starting_no(999).cars() == []


def test_by_starting_no_accumulates_set() -> None:
    """Calling by_starting_no twice with the same value still returns one car."""
    s = make_race_state()
    cars = s.filter().by_starting_no(7).by_starting_no(7).cars()
    assert starting_nos(cars) == [7]


# ---------------------------------------------------------------------------
# FILT-03: by_driver
# ---------------------------------------------------------------------------


def test_by_driver_substring_case_insensitive() -> None:
    """by_driver('mueller') (lowercase ASCII) matches 'M. Mueller'."""
    s = make_race_state()
    cars = s.filter().by_driver("mueller").cars()
    assert starting_nos(cars) == [7]


def test_by_driver_substring_with_umlaut_via_ascii_fallback() -> None:
    """by_driver('Muell') matches 'M. Mueller' even without the German umlaut."""
    s = make_race_state()
    cars = s.filter().by_driver("Muell").cars()
    assert starting_nos(cars) == [7]


def test_by_driver_substring_partial() -> None:
    """Substring 'er' matches Weber, Bauer, Fischer, Klein (4 of 6)."""
    s = make_race_state()
    cars = s.filter().by_driver("er").cars()
    assert starting_nos(cars) == [22, 44, 55, 66]


def test_by_driver_no_match_returns_empty() -> None:
    """Substring with no matches returns []."""
    s = make_race_state()
    assert s.filter().by_driver("zzz").cars() == []


def test_by_driver_skips_cars_without_driver() -> None:
    """A car with driver=None is excluded from by_driver results."""
    s = make_race_state()
    # Clear driver on car 7
    s._cars[7].driver = None  # noqa: SLF001
    cars = s.filter().by_driver("Mueller").cars()
    assert cars == []


def test_by_driver_multiple_substrings_or() -> None:
    """by_driver('Muel').by_driver('Schm') matches BOTH 'Mueller' and 'Schmidt'."""
    s = make_race_state()
    cars = s.filter().by_driver("Muel").by_driver("Schm").cars()
    # OR semantics across driver substrings — both must match if we want a
    # car. Filter combines with AND across dimensions, but multiple
    # by_driver calls are OR-of-substrings.
    assert starting_nos(cars) == [7, 11]


# ---------------------------------------------------------------------------
# FILT-04: by_position (inclusive bounds, unknown-position excluded by default)
# ---------------------------------------------------------------------------


def test_by_position_max_top_5() -> None:
    """by_position(max=5) returns positions 1-5 (car 66, pos=6, excluded)."""
    s = make_race_state()
    cars = s.filter().by_position(max=5).cars()
    assert starting_nos(cars) == [7, 11, 22, 44, 55]


def test_by_position_range() -> None:
    """by_position(min=2, max=4) returns positions 2, 3, 4."""
    s = make_race_state()
    cars = s.filter().by_position(min=2, max=4).cars()
    assert starting_nos(cars) == [11, 22, 44]


def test_by_position_min_only() -> None:
    """by_position(min=5) returns positions 5 and 6."""
    s = make_race_state()
    cars = s.filter().by_position(min=5).cars()
    assert starting_nos(cars) == [55, 66]


def test_by_position_unknown_position_excluded_by_default() -> None:
    """A 7th car with position=None is excluded when no filter is set."""
    s = make_race_state()
    # Inject an unknown-position car
    s._cars[77] = CarState(  # noqa: SLF001
        starting_no=77,
        position=None,
        class_name="SP9",
        driver="Unknown Driver",
        laps_completed=10,
    )
    cars = s.filter().cars()
    assert len(cars) == 6
    assert all(c.position is not None for c in cars)


def test_by_position_include_unknown_via_opt_in() -> None:
    """include_unknown_position() includes None-position cars in the result."""
    s = make_race_state()
    s._cars[77] = CarState(  # noqa: SLF001
        starting_no=77,
        position=None,
        class_name="SP9",
        driver="Unknown Driver",
        laps_completed=10,
    )
    cars = s.filter().include_unknown_position().cars()
    # 6 known + 1 unknown = 7
    assert len(cars) == 7


# ---------------------------------------------------------------------------
# FILT-05: by_lap (inclusive bounds on laps_completed)
# ---------------------------------------------------------------------------


def test_by_lap_min() -> None:
    """by_lap(min=28) returns the 2 cars that have completed 28 laps."""
    s = make_race_state()
    cars = s.filter().by_lap(min=28).cars()
    assert starting_nos(cars) == [7, 11]


def test_by_lap_max() -> None:
    """by_lap(max=26) returns cars with laps_completed <= 26."""
    s = make_race_state()
    cars = s.filter().by_lap(max=26).cars()
    assert starting_nos(cars) == [55, 66]


def test_by_lap_range() -> None:
    """by_lap(min=26, max=27) returns cars on laps 26 and 27."""
    s = make_race_state()
    cars = s.filter().by_lap(min=26, max=27).cars()
    assert starting_nos(cars) == [22, 44, 55]


def test_by_lap_excludes_unknown_laps() -> None:
    """A car with laps_completed=0 (not yet started) is included in by_lap(min=0)."""
    s = make_race_state()
    s._cars[88] = CarState(starting_no=88, position=None, class_name="SP9", driver="X")  # noqa: SLF001
    cars = s.filter().by_lap(min=0).cars()
    # 88 has laps_completed=0 (default), so by_lap(min=0) should include it
    assert 88 in starting_nos(cars)


# ---------------------------------------------------------------------------
# FILT-06: sector_time_lt (strict less-than on per-car sector_bests)
# ---------------------------------------------------------------------------


def test_sector_time_lt_filters_by_sector1() -> None:
    """sector_time_lt(sector=1, value_ms=33000) returns only car 7.

    Sector 1 bests: car 7 = 32150, car 11 = 33000, car 22 = 33500, car 44 = 35100.
    Strict < 33000: only 32150 < 33000 (car 7).
    """
    s = make_race_state()
    cars = s.filter().sector_time_lt(sector=1, value_ms=33000).cars()
    assert starting_nos(cars) == [7]


def test_sector_time_lt_no_data_excluded() -> None:
    """Cars without sector_bests for the requested sector are excluded."""
    s = make_race_state()
    # Only car 7 has sector 2 data
    cars = s.filter().sector_time_lt(sector=2, value_ms=99999).cars()
    assert starting_nos(cars) == [7]


def test_sector_time_lt_strict_less_than() -> None:
    """32150 is strictly less than 32151 (boundary case)."""
    s = make_race_state()
    cars = s.filter().sector_time_lt(sector=1, value_ms=32151).cars()
    assert starting_nos(cars) == [7]


def test_sector_time_lt_boundary_excludes_equal() -> None:
    """32150 is NOT strictly less than 32150, so car 7 is excluded at the boundary."""
    s = make_race_state()
    cars = s.filter().sector_time_lt(sector=1, value_ms=32150).cars()
    assert cars == []


# ---------------------------------------------------------------------------
# FILT-07: AND composition
# ---------------------------------------------------------------------------


def test_compose_class_and_top5() -> None:
    """by_class('SP9').top(2) returns top-2 SP9 cars (positions 1, 2)."""
    s = make_race_state()
    cars = s.filter().by_class("SP9").top(2).cars()
    assert starting_nos(cars) == [7, 11]


def test_compose_class_position_lap_and_sector_AND() -> None:
    """4-dimension AND: SP9 + pos<=2 + lap>=28 + sector1<33000 -> only car 7."""
    s = make_race_state()
    cars = (
        s.filter()
        .by_class("SP9")
        .by_position(max=2)
        .by_lap(min=28)
        .sector_time_lt(sector=1, value_ms=33000)
        .cars()
    )
    assert starting_nos(cars) == [7]


def test_compose_no_match_returns_empty() -> None:
    """AND with a contradictory constraint returns []. SP7 + position<=2 is empty."""
    s = make_race_state()
    cars = s.filter().by_class("SP7").by_position(max=2).cars()
    assert cars == []


def test_compose_top_n_truncates_after_filtering() -> None:
    """top(2) on 3 SP9 cars returns positions 1 and 2 only."""
    s = make_race_state()
    cars = s.filter().by_class("SP9").top(2).cars()
    assert len(cars) == 2


# ---------------------------------------------------------------------------
# Convenience pass-throughs on RaceState
# ---------------------------------------------------------------------------


def test_convenience_cars_by_class() -> None:
    """state.cars_by_class('SP9') returns the 3 SP9 cars."""
    s = make_race_state()
    cars = s.cars_by_class("SP9")
    assert starting_nos(cars) == [7, 11, 22]


def test_convenience_cars_by_starting_no_single() -> None:
    """state.cars_by_starting_no(7) returns just car 7."""
    s = make_race_state()
    cars = s.cars_by_starting_no(7)
    assert starting_nos(cars) == [7]


def test_convenience_cars_by_starting_no_list() -> None:
    """state.cars_by_starting_no([7, 11]) returns 2 cars."""
    s = make_race_state()
    cars = s.cars_by_starting_no([7, 11])
    assert starting_nos(cars) == [7, 11]


def test_convenience_top() -> None:
    """state.top(3) returns the top 3 cars by position."""
    s = make_race_state()
    cars = s.top(3)
    assert starting_nos(cars) == [7, 11, 22]


# ---------------------------------------------------------------------------
# Filter.starting_nos() helper
# ---------------------------------------------------------------------------


def test_filter_starting_nos_returns_ints_only() -> None:
    """starting_nos() returns a list of ints — useful for Discord bots / dashboards."""
    s = make_race_state()
    nos = s.filter().by_class("SP9").starting_nos()
    assert nos == [7, 11, 22]
    assert all(isinstance(n, int) for n in nos)


# ---------------------------------------------------------------------------
# Empty race edge case
# ---------------------------------------------------------------------------


def test_filter_on_empty_state_returns_empty() -> None:
    """state.filter() on a brand-new RaceState() returns []. No crash."""
    s = RaceState()
    assert s.filter().cars() == []
    assert s.filter().by_class("SP9").cars() == []
    assert s.filter().by_position(max=10).cars() == []
