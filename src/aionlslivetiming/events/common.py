"""Shared embedded value types for the 8 Message dataclasses.

All types in this module are :func:`dataclasses.dataclass` instances with
``frozen=True, slots=True`` per D-01 (no pydantic, no attrs on the events
layer — stdlib only). They are constructed by the parser (Plan 03) from
short-code server JSON; consumers never build them by hand in normal use.

Per D-03 every optional field uses ``Optional[...]`` (or a tuple defaulting
to ``()``) so the parser never crashes on missing server fields.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TimeOfDay:
    """Race-clock time-of-day in milliseconds since session start.

    The NLS server emits ``TOD`` and ``ENDTIME`` payloads as
    ``{"value": <ms>}``; the parser maps that to this dataclass. Only the
    integer ``value_ms`` is retained — the server does not publish an
    associated timezone or wall-clock timestamp.
    """

    value_ms: int


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """Session/heat identification carried in PID 0 (initial state).

    All fields except ``session`` are optional — the server may omit
    ``starting_no``, ``heat``, ``heat_type``, ``cup``, or ``event_id``
    depending on the race week.
    """

    session: str
    starting_no: int | None = None
    heat: str | None = None
    heat_type: str | None = None
    cup: str | None = None
    event_id: str | None = None


@dataclass(frozen=True, slots=True)
class BestSector:
    """One entry in the ``BEST`` array of a result/statistics payload.

    Carried by ``InitialStateMessage.best_sectors`` and
    ``StatisticsMessage.best_sectors``. ``driver`` is optional because
    the server sometimes publishes the time before attaching a driver.
    """

    starting_no: int
    sector: int
    value_ms: int
    driver: str | None = None


@dataclass(frozen=True, slots=True)
class CarResult:
    """One row of a result table (positions, lap counts, gaps).

    Used by ``InitialStateMessage.results``, ``QualifyingMessage.results``,
    ``StatisticsMessage.leading`` and ``StatisticsMessage.best_laps``.
    All non-positional fields are optional per D-03 — the parser must
    never crash on a partial row.
    """

    starting_no: int
    position: int
    class_name: str | None = None
    driver: str | None = None
    laps: int = 0
    total_time_ms: int | None = None
    gap_to_leader_ms: int | None = None
    best_lap_ms: int | None = None
