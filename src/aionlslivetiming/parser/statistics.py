"""Parser for PID 9002 (statistics).

Maps the NLS server's PID 9002 payload (``LEADING``, ``BEST_LAPS``,
``BEST_SECTORS``) onto :class:`StatisticsMessage`. Each of the three
sub-tables is independent and defaults to an empty tuple so any
combination parses cleanly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aionlslivetiming.events.statistics import StatisticsMessage
from aionlslivetiming.parser._helpers import _best_sector, _car_result

__all__ = ["parse_pid_9002"]

_EVENT_PID = 9002


def parse_pid_9002(raw: Mapping[str, Any]) -> StatisticsMessage:
    """Parse a PID 9002 payload into a :class:`StatisticsMessage`."""
    return StatisticsMessage(
        leading=tuple(_car_result(r) for r in (raw.get("LEADING") or ())),
        best_laps=tuple(_car_result(r) for r in (raw.get("BEST_LAPS") or ())),
        best_sectors=tuple(_best_sector(b) for b in (raw.get("BEST_SECTORS") or ())),
        raw=dict(raw),
    )
