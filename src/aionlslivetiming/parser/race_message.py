"""Parser for PID 3 (race messages).

Maps the NLS server's PID 3 payload (``text``, ``type``, ``startingNo``,
``session``) onto :class:`RaceMessage`. ``type`` is mapped to the
``category`` field; ``session`` is the race session id (e.g. ``"R1"``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aionlslivetiming.events.race_message import RaceMessage
from aionlslivetiming.parser._helpers import _opt_int, _opt_str, warn_missing

__all__ = ["parse_pid_3"]

_EVENT_PID = 3


def parse_pid_3(raw: Mapping[str, Any]) -> RaceMessage:
    """Parse a PID 3 payload into a :class:`RaceMessage`."""
    if "text" not in raw:
        warn_missing("text", _EVENT_PID)
    if "type" not in raw:
        warn_missing("type", _EVENT_PID)

    return RaceMessage(
        text=str(raw.get("text", "")),
        category=str(raw.get("type", "INFO")),
        starting_no=_opt_int(raw.get("startingNo")),
        session=_opt_str(raw.get("session")),
        raw=dict(raw),
    )
