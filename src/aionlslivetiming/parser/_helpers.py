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
from typing import TYPE_CHECKING, Any

from aionlslivetiming.events.common import BestSector, CarResult, SessionInfo, TimeOfDay
from aionlslivetiming.logging import get_logger

if TYPE_CHECKING:
    pass

__all__ = [
    "_best_sector",
    "_car_result",
    "_opt_int",
    "_opt_str",
    "_session_info",
    "_time_of_day",
    "reset_warned",
    "warn_missing",
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


def _opt_int(v: Any) -> int | None:
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


def _pick(r: Mapping[str, Any], *keys: str) -> Any:
    """Return the first non-``None`` value among the given keys.

    Unlike ``r.get(k1) or r.get(k2)``, this preserves legitimate
    falsy values like ``0`` and ``""`` — those are real server data,
    not "missing".
    """
    for k in keys:
        v = r.get(k)
        if v is not None:
            return v
    return None


def _parse_lap_time_ms(v: Any) -> int | None:
    """Coerce a lap-time field to milliseconds.

    The server emits lap times in two formats:

    - Plain integer / numeric string (already milliseconds)
    - ``"MM:SS.sss"`` (display format) — converted to total milliseconds
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if ":" in s:
            import re
            m = re.match(r"^(\d+):(\d+(?:\.\d+)?)$", s)
            if m:
                return int((int(m.group(1)) * 60 + float(m.group(2))) * 1000)
            return None
        try:
            return int(s)
        except ValueError:
            return None
    return None


def _opt_str(v: Any) -> str | None:
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


def _car_result(r: Any) -> CarResult:
    """Build a :class:`CarResult` from a single ``RESULT``/``LEADING``/``BEST_LAPS`` row.

    The server emits two key naming conventions:

    - Modern SPA: ``startingNo``, ``position``, ``class``, ``driver``,
      ``laps``, ``totalTime``, ``gap``, ``best``
    - Older / alternative: ``STNR``, ``POSITION``, ``CLASSNAME``, ``NAME``,
      ``LAPS``, ``INT``, ``GAP``, ``FASTESTLAP``

    Both shapes are accepted. All values are strings; ``int()`` casts
    on bad input fall back to ``0``/``None`` per D-03. Non-Mapping
    rows return a placeholder rather than raising.
    """
    if not isinstance(r, Mapping):
        return CarResult(starting_no=0, position=0)

    starting_no = _opt_int(_pick(r, "startingNo", "STNR")) or 0
    position = _opt_int(_pick(r, "position", "POSITION")) or 0
    class_name = _opt_str(_pick(r, "class", "CLASSNAME"))
    driver = _opt_str(_pick(r, "driver", "NAME"))
    laps = _opt_int(_pick(r, "laps", "LAPS")) or 0
    total_time_ms = _opt_int(_pick(r, "totalTime", "INT"))
    gap_to_leader_ms = _opt_int(_pick(r, "gap", "GAP"))
    best_lap_ms = _parse_lap_time_ms(_pick(r, "best", "FASTESTLAP"))

    return CarResult(
        starting_no=starting_no,
        position=position,
        class_name=class_name,
        driver=driver,
        laps=laps,
        total_time_ms=total_time_ms,
        gap_to_leader_ms=gap_to_leader_ms,
        best_lap_ms=best_lap_ms,
    )


def _best_sector(b: Any) -> BestSector:
    """Build a :class:`BestSector` from a single ``BEST``/``BEST_SECTORS`` row.

    ``startingNo``, ``sector`` and ``value`` are required to be present
    and cast to int; ``driver`` is optional. A missing or non-numeric
    ``startingNo``/``sector``/``value`` falls back to ``0`` (D-03).

    Non-Mapping rows return a placeholder rather than raising.
    """
    if not isinstance(b, Mapping):
        return BestSector(starting_no=0, sector=0, value_ms=0)
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
