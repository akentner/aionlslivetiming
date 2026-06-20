"""Parser for PID 0 (initial state / ongoing race positions).

Maps the NLS server's short-code PID 0 payload (carrying the per-car
lap counts, sector times, gaps, positions, best-sector table and
session identification) onto :class:`InitialStateMessage`.

Per D-03 every optional field is handled with safe defaults — the
parser never raises on missing or malformed input. Per PARSE-03 the
original ``raw`` payload is preserved verbatim.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aionlslivetiming.events.initial_state import InitialStateMessage
from aionlslivetiming.parser._helpers import (
    _best_sector,
    _car_result,
    _session_info,
    warn_missing,
)

__all__ = ["parse_pid_0"]

_EVENT_PID = 0


def parse_pid_0(raw: Mapping[str, Any]) -> InitialStateMessage:
    """Parse a PID 0 payload into an :class:`InitialStateMessage`.

    ``PID``/``VER``/``EXPORTID``/``TRACKNAME`` default to ``0``/``""`` on
    absence. ``RESULT``/``BEST`` default to empty tuples. ``LTS_NOT_FOUND``
    surfaces as a boolean flag on the message so the connection layer
    can react (CONN-05).
    """
    pid_raw = raw.get("PID")
    try:
        pid = int(pid_raw) if pid_raw is not None else 0
    except (TypeError, ValueError):
        pid = 0
        warn_missing("PID", _EVENT_PID)

    if "TRACKNAME" not in raw:
        warn_missing("TRACKNAME", _EVENT_PID)
    if "EXPORTID" not in raw:
        warn_missing("EXPORTID", _EVENT_PID)

    return InitialStateMessage(
        pid=pid,
        ver=str(raw.get("VER", "")),
        export_id=str(raw.get("EXPORTID", "")),
        track_name=str(raw.get("TRACKNAME", "")),
        session=_session_info(raw),
        results=tuple(_car_result(r) for r in (raw.get("RESULT") or ())),
        best_sectors=tuple(_best_sector(b) for b in (raw.get("BEST") or ())),
        lts_not_found=bool(raw.get("LTS_NOT_FOUND", False)),
        raw=dict(raw),
    )
