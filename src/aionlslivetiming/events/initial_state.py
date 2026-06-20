"""Initial-state message (PID 0).

The NLS server sends a single PID 0 frame after the WebSocket handshake
that carries the event's full initial state: track name, session
identification, the current ``RESULT`` table (with positions, lap
counts, gaps, best laps), and the ``BEST`` sector-time table.

``LTS_NOT_FOUND: true`` is the server's signal that the requested event
id is unknown (CONN-05); the parser surfaces that as
``lts_not_found=True`` on this message rather than discarding the frame.

Per D-03 missing ``RESULT``/``BEST`` arrays default to empty tuples.
Unknown server keys are preserved verbatim in ``raw`` so future schema
additions round-trip cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping

    from aionlslivetiming.events.common import BestSector, CarResult, SessionInfo


@dataclass(frozen=True, slots=True)
class InitialStateMessage:
    """PID 0: initial event state (results, best sectors, session info)."""

    event_pid: ClassVar[int] = 0

    pid: int
    ver: str
    export_id: str
    track_name: str
    session: SessionInfo
    results: tuple[CarResult, ...] = ()
    best_sectors: tuple[BestSector, ...] = ()
    lts_not_found: bool = False
    raw: Mapping[str, Any] = field(default_factory=dict)
