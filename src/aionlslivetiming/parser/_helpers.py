"""Shared private helpers for the per-PID parsers.

D-03: WARNING logs are deduped per ``(event_pid, field_name)`` tuple.
The dedupe set is shared across every parser so a hot feed emitting the
same gap repeatedly only logs once per process per field.

These helpers are intentionally permissive — every field lookup uses
safe defaults (empty tuple, empty string, ``None``) so the parser never
raises on a partial server payload (D-03).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Optional

from aionlslivetiming.events.common import BestSector, CarResult, SessionInfo, TimeOfDay
from aionlslivetiming.logging import get_logger

if TYPE_CHECKING:
    pass

__all__ = [
    "reset_warned",
    "warn_missing",
    "_opt_int",
    "_opt_str",
    "_time_of_day",
    "_session_info",
    "_car_result",
    "_best_sector",
]

# Shared dedupe set (D-03). The ``(event_pid, field_name)`` tuple is the
# unique key — once a field has been warned-on for a given PID, repeated
# missing-field events emit no extra log.
_warned: set[tuple[int, str]] = set()

# One logger per parser subpackage. Per the docstring in
# ``aionlslivetiming.logging`` the canonical namespace is
# ``aionlslivetiming.parser``.
logger = get_logger("aionlslivetiming.parser")


def reset_warned() -> None:
    """Clear the dedupe set. Test-only — allows independent test cases."""
    _warned.clear()


def warn_missing(field_name: str, event_pid: int) -> None:
    """Log a WARNING once per unique ``(event_pid, field_name)`` pair.

    Per D-03 the parser never raises on missing or malformed input —
    instead it surfaces a single WARNING line per gap. Repeated gaps for
    the same field on the same PID emit no extra log.
    """
    key = (event_pid, field_name)
    if key in _warned:
        return
    _warned.add(key)
    logger.warning("missing field %r for eventPid=%d", field_name, event_pid)


def _opt_int(v: Any) -> Optional[int]:
    """Return ``int(v)`` if *v* is not ``None``, else ``None``.

    Returns ``None`` on ``ValueError``/``TypeError`` so the parser never
    crashes on a malformed integer (D-03).
    """
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _opt_str(v: Any) -> Optional[str]:
    """Return ``str(v)`` if *v* is not ``None``, else ``None``.

    Returns ``None`` on ``TypeError`` (D-03).
    """
    if v is None:
        return None
    try:
        return str(v)
    except TypeError:
        return None


def _time_of_day(v: Mapping[str, Any]) -> TimeOfDay:
    """Construct :class:`TimeOfDay` from a ``{"value": <ms>}`` dict."""
    return TimeOfDay(value_ms=int(v.get("value", 0)))


def _session_info(raw: Mapping[str, Any]) -> SessionInfo:
    """Build a :class:`SessionInfo` from a PID 0 payload.

    Reads ``SESSION`` (required), ``startingNo``, ``HEAT``, ``HEATTYPE``,
    ``CUP``, and ``EXPORTID`` (mapped to ``event_id``). Every optional
    field defaults to ``None`` (D-03).
    """
    return SessionInfo(
        session=str(raw.get("SESSION", "")),
        starting_no=_opt_int(raw.get("startingNo")),
        heat=_opt_str(raw.get("HEAT")),
        heat_type=_opt_str(raw.get("HEATTYPE")),
        cup=_opt_str(raw.get("CUP")),
        event_id=_opt_str(raw.get("EXPORTID")),
    )


def _car_result(r: Mapping[str, Any]) -> CarResult:
    """Build a :class:`CarResult` from a single ``RESULT``/``LEADING``/``BEST_LAPS`` row.

    ``startingNo`` and ``position`` are required to be present and
    cast to int; everything else is optional and defaults to ``None`` /
    ``0`` (D-03). A missing or non-numeric ``startingNo``/``position``
    falls back to ``0`` so the parser still returns a valid CarResult
    rather than raising.
    """
    starting_no_raw = r.get("startingNo")
    position_raw = r.get("position")
    try:
        starting_no = int(starting_no_raw) if starting_no_raw is not None else 0
    except (TypeError, ValueError):
        starting_no = 0
    try:
        position = int(position_raw) if position_raw is not None else 0
    except (TypeError, ValueError):
        position = 0
    return CarResult(
        starting_no=starting_no,
        position=position,
        class_name=_opt_str(r.get("class")),
        driver=_opt_str(r.get("driver")),
        laps=_opt_int(r.get("laps")) or 0,
        total_time_ms=_opt_int(r.get("totalTime")),
        gap_to_leader_ms=_opt_int(r.get("gap")),
        best_lap_ms=_opt_int(r.get("best")),
    )


def _best_sector(b: Mapping[str, Any]) -> BestSector:
    """Build a :class:`BestSector` from a single ``BEST``/``BEST_SECTORS`` row.

    ``startingNo``, ``sector`` and ``value`` are required to be present
    and cast to int; ``driver`` is optional. A missing or non-numeric
    ``startingNo``/``sector``/``value`` falls back to ``0`` (D-03).
    """
    starting_no_raw = b.get("startingNo")
    sector_raw = b.get("sector")
    value_raw = b.get("value")
    try:
        starting_no = int(starting_no_raw) if starting_no_raw is not None else 0
    except (TypeError, ValueError):
        starting_no = 0
    try:
        sector = int(sector_raw) if sector_raw is not None else 0
    except (TypeError, ValueError):
        sector = 0
    try:
        value_ms = int(value_raw) if value_raw is not None else 0
    except (TypeError, ValueError):
        value_ms = 0
    return BestSector(
        starting_no=starting_no,
        sector=sector,
        value_ms=value_ms,
        driver=_opt_str(b.get("driver")),
    )
