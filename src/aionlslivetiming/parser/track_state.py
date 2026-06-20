"""Parser for PID 4 (track state).

Maps the NLS server's PID 4 payload (``TRACKSTATE``, ``TIMESTATE``,
``TOD``, ``ENDTIME``) onto :class:`TrackStateMessage`.

Per D-03 ``TRACKSTATE``/``TIMESTATE`` default to ``""`` on absence.
``TOD``/``ENDTIME`` default to ``None`` (they are mapped from
``{"value": <ms>}`` sub-dicts).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aionlslivetiming.events.track_state import TrackStateMessage
from aionlslivetiming.parser._helpers import _time_of_day, warn_missing

__all__ = ["parse_pid_4"]

_EVENT_PID = 4


def parse_pid_4(raw: Mapping[str, Any]) -> TrackStateMessage:
    """Parse a PID 4 payload into a :class:`TrackStateMessage`."""
    if "TRACKSTATE" not in raw:
        warn_missing("TRACKSTATE", _EVENT_PID)
    if "TIMESTATE" not in raw:
        warn_missing("TIMESTATE", _EVENT_PID)

    tod_raw = raw.get("TOD")
    end_raw = raw.get("ENDTIME")
    return TrackStateMessage(
        track_state=str(raw.get("TRACKSTATE", "")),
        time_state=str(raw.get("TIMESTATE", "")),
        tod=_time_of_day(tod_raw) if isinstance(tod_raw, Mapping) else None,
        end_time=_time_of_day(end_raw) if isinstance(end_raw, Mapping) else None,
        raw=dict(raw),
    )
