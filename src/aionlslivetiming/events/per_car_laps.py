"""Per-car laps message (PID 7).

PID 7 frames are subscription-targeted per-car lap drilldown: the
client sends a handshake with ``{"eventId", "eventPid": 7, "session",
"startingNo"}`` and the server responds with one or more frames whose
``laps`` array carries raw lap dicts (``{lap, time, s1, s2, s3}``).

Per D-03 individual lap dicts are preserved verbatim in ``laps`` —
parsing lap fields into a typed structure is Phase 2 (state cache)
work, not Phase 1. The ``laps`` tuple defaults to ``()`` so a frame
without a ``laps`` key (e.g. a "car retired" notification) parses
cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class PerCarLapsMessage:
    """PID 7: per-car lap drilldown (one raw dict per lap)."""

    event_pid: ClassVar[int] = 7

    session: str
    starting_no: int
    laps: tuple[Mapping[str, Any], ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)
