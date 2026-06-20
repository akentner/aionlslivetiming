"""Composable filter DSL over :class:`~aionlslivetiming.state.race_state.RaceState`.

The :class:`Filter` is the read API for downstream consumers
(Discord bots, dashboards, Home Assistant). It exposes six independent
filter dimensions that AND-combine into one query result:

- :meth:`Filter.by_class` — ``class_name == X``
- :meth:`Filter.by_starting_no` — ``starting_no in {X, Y, ...}``
- :meth:`Filter.by_driver` — case-insensitive substring on ``driver``
- :meth:`Filter.by_position` — inclusive ``[min, max]`` on ``position``
- :meth:`Filter.by_lap` — inclusive ``[min, max]`` on ``laps_completed``
- :meth:`Filter.sector_time_lt` — strict less-than on per-car sector best

Calling :meth:`Filter.cars` materialises the result as a list of
:class:`~aionlslivetiming.state.car.CarState` ordered by position
(``None`` positions last). Methods return ``self`` for chaining
(builder pattern) and are idempotent — calling ``by_class('SP9')``
twice has no extra effect (set semantics).

Per :class:`aionlslivetiming.state.race_state.RaceState`'s public
API surface this module also exposes convenience pass-throughs
(``cars_by_class``, ``top``) so consumers can choose the method-on-cache
shape if they prefer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from aionlslivetiming.state.car import CarState
    from aionlslivetiming.state.race_state import RaceState


class Filter:
    """Composable query object over :class:`RaceState`. AND-semantics across dimensions.

    Each filter method narrows the working set; calling :meth:`cars`
    materialises the result as a list of :class:`CarState` ordered by
    ``position`` (None positions last). Methods return ``self`` so
    they can be chained::

        state.filter().by_class("SP9").top(5).cars()

    The driver dimension accumulates substrings (OR semantics across
    substrings — a car matches if ANY substring matches its driver
    string, case-insensitively). All other dimensions use the latest
    value (single-value setter).
    """

    def __init__(self, state: RaceState) -> None:
        self._state = state
        self._class_eq: set[str] = set()
        self._starting_no_in: set[int] | None = None
        self._driver_substr_lower: list[str] = []
        self._pos_min: int | None = None
        self._pos_max: int | None = None
        self._include_unknown_position: bool = False
        self._lap_min: int | None = None
        self._lap_max: int | None = None
        self._sector_lt: tuple[int, int] | None = None  # (sector, value_ms) strict less-than
        self._top_n: int | None = None

    # ---- dimension setters (each returns self for chaining) ----
    def by_class(self, class_name: str) -> Filter:
        """Narrow to cars whose ``class_name`` is exactly ``class_name``.

        Accumulating — calling twice with different values broadens
        the working set (set union semantics).
        """
        self._class_eq.add(class_name)
        return self

    def by_starting_no(self, value: int | Iterable[int]) -> Filter:
        """Narrow to cars whose ``starting_no`` is in ``{X, Y, ...}``.

        ``value`` may be a single ``int`` or any iterable of ints.
        Accumulating (set union semantics).
        """
        if self._starting_no_in is None:
            self._starting_no_in = set()
        if isinstance(value, int):
            self._starting_no_in.add(value)
        else:
            self._starting_no_in.update(int(v) for v in value)
        return self

    def by_driver(self, substring: str) -> Filter:
        """Narrow to cars whose driver string contains ``substring`` (case-insensitive).

        OR-semantics across substrings — calling twice with two
        different substrings keeps cars that match EITHER substring.
        """
        self._driver_substr_lower.append(substring.lower())
        return self

    def by_position(self, *, min: int | None = None, max: int | None = None) -> Filter:
        """Narrow to cars whose position is in the inclusive ``[min, max]`` range.

        Unknown-position cars (position is ``None``) are excluded by
        default; call :meth:`include_unknown_position` to opt them in.
        """
        self._pos_min = min
        self._pos_max = max
        return self

    def by_lap(self, *, min: int | None = None, max: int | None = None) -> Filter:
        """Narrow to cars whose ``laps_completed`` is in the inclusive ``[min, max]`` range."""
        self._lap_min = min
        self._lap_max = max
        return self

    def sector_time_lt(self, *, sector: int, value_ms: int) -> Filter:
        """Narrow to cars whose best sector-``sector`` time is strictly less than ``value_ms``.

        Cars with no data for ``sector`` are excluded.
        """
        self._sector_lt = (sector, value_ms)
        return self

    def include_unknown_position(self) -> Filter:
        """Opt-in: keep cars whose ``position`` is ``None`` in the result.

        By default, unknown-position cars are excluded (no position
        rank available).
        """
        self._include_unknown_position = True
        return self

    def top(self, n: int) -> Filter:
        """Limit the result to the first ``n`` cars (in position order)."""
        self._top_n = n
        return self

    # ---- terminal: materialise the result ----
    def cars(self) -> list[CarState]:
        """Materialise the filtered result as a list of :class:`CarState`.

        Ordered by ``position`` ascending; ``None`` positions go last
        (matches :meth:`RaceState.standings`).
        """
        result: list[CarState] = list(self._state.cars.values())

        if self._class_eq:
            result = [c for c in result if c.class_name in self._class_eq]
        if self._starting_no_in is not None:
            result = [c for c in result if c.starting_no in self._starting_no_in]
        if self._driver_substr_lower:
            subs = self._driver_substr_lower

            def driver_match(c: CarState) -> bool:
                if c.driver is None:
                    return False
                d = c.driver.lower()
                return any(sub in d for sub in subs)

            result = [c for c in result if driver_match(c)]
        if (
            self._pos_min is not None
            or self._pos_max is not None
            or not self._include_unknown_position
        ):
            pos_min = self._pos_min
            pos_max = self._pos_max
            include_unknown = self._include_unknown_position

            def pos_match(c: CarState) -> bool:
                if c.position is None:
                    return include_unknown
                if pos_min is not None and c.position < pos_min:
                    return False
                return not (pos_max is not None and c.position > pos_max)

            result = [c for c in result if pos_match(c)]
        if self._lap_min is not None or self._lap_max is not None:
            lap_min = self._lap_min
            lap_max = self._lap_max

            def lap_match(c: CarState) -> bool:
                if lap_min is not None and c.laps_completed < lap_min:
                    return False
                return not (lap_max is not None and c.laps_completed > lap_max)

            result = [c for c in result if lap_match(c)]
        if self._sector_lt is not None:
            sec, threshold = self._sector_lt

            def sector_match(c: CarState) -> bool:
                v = c.sector_bests.get(sec)
                return v is not None and v < threshold

            result = [c for c in result if sector_match(c)]

        # Order: by position ascending, None last (matches RaceState.standings())
        result.sort(key=lambda c: (c.position is None, c.position if c.position is not None else 0))

        if self._top_n is not None:
            result = result[: self._top_n]
        return result

    # ---- terminal convenience: returning starting_nos only ----
    def starting_nos(self) -> list[int]:
        """Return only the starting numbers of the filtered cars.

        Useful for Discord bots / dashboards that just need a list of
        car numbers to render.
        """
        return [c.starting_no for c in self.cars()]
