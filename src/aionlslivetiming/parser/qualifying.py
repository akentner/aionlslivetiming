"""Parser for PID 501 (qualifying).

Maps the NLS server's PID 501 payload (``RESULT`` array of
``startingNo``/``position``/``class``/``driver``/``best`` rows) onto
:class:`QualifyingMessage`. Each row is a :class:`CarResult` with
``laps=0``, ``total_time_ms=None``, ``gap_to_leader_ms=None`` and
``best_lap_ms`` set from the row's ``best`` field.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aionlslivetiming.events.qualifying import QualifyingMessage
from aionlslivetiming.parser._helpers import _car_result

__all__ = ["parse_pid_501"]

_EVENT_PID = 501


def parse_pid_501(raw: Mapping[str, Any]) -> QualifyingMessage:
    """Parse a PID 501 payload into a :class:`QualifyingMessage`."""
    return QualifyingMessage(
        results=tuple(_car_result(r) for r in (raw.get("RESULT") or ())),
        raw=dict(raw),
    )
