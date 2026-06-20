"""Parser for the ``{"type": "time", "value": <ms>}`` time-sync frame.

The NLS server's first WebSocket frame is a time-sync ping (not a
PID-discriminated event) used by the client to measure round-trip
latency. The parser dispatcher routes by the ``type`` field rather
than ``eventPid``; this function is the leaf for that branch.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aionlslivetiming.events.time_sync import TimeSyncMessage
from aionlslivetiming.parser._helpers import warn_missing

__all__ = ["parse_time_sync"]

# TimeSyncMessage.event_pid is the -1 sentinel — the dispatcher never
# matches it against a real PID, it routes by the type field instead.
_EVENT_PID = -1


def parse_time_sync(raw: Mapping[str, Any]) -> TimeSyncMessage:
    """Parse a ``{"type": "time", "value": <ms>}`` frame into a :class:`TimeSyncMessage`."""
    value_raw = raw.get("value")
    try:
        value_ms = int(value_raw) if value_raw is not None else 0
    except (TypeError, ValueError):
        value_ms = 0
        warn_missing("value", _EVENT_PID)
    return TimeSyncMessage(
        value_ms=value_ms,
        raw=dict(raw),
    )
