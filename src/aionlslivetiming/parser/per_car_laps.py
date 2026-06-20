"""Parser for PID 7 (per-car laps).

Maps the NLS server's PID 7 payload (``session``, ``startingNo``,
``laps``) onto :class:`PerCarLapsMessage`. Per D-03 individual lap
dicts are preserved verbatim in the ``laps`` tuple — typed lap
parsing is Phase 2 (state cache) work.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aionlslivetiming.events.per_car_laps import PerCarLapsMessage
from aionlslivetiming.parser._helpers import warn_missing

__all__ = ["parse_pid_7"]

_EVENT_PID = 7


def parse_pid_7(raw: Mapping[str, Any]) -> PerCarLapsMessage:
    """Parse a PID 7 payload into a :class:`PerCarLapsMessage`."""
    starting_no_raw = raw.get("startingNo")
    try:
        starting_no = int(starting_no_raw) if starting_no_raw is not None else 0
    except (TypeError, ValueError):
        starting_no = 0
        warn_missing("startingNo", _EVENT_PID)

    if "session" not in raw:
        warn_missing("session", _EVENT_PID)

    laps_raw = raw.get("laps") or ()
    return PerCarLapsMessage(
        session=str(raw.get("session", "")),
        starting_no=starting_no,
        laps=tuple(dict(lap) for lap in laps_raw if isinstance(lap, Mapping)),
        raw=dict(raw),
    )
