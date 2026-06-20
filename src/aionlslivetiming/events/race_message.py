"""Race-message event (PID 3).

PID 3 frames carry ad-hoc race-control text — pit-in/pit-out notices,
yellow/red flag declarations, penalty decisions, sector bests. The
``category`` field is the server's ``type`` field (``"PIT"``,
``"FLAG"``, ``"PENALTY"``, ``"INFO"``); kept as ``str`` for the same
forward-compatibility reason as :class:`TrackStateMessage.track_state`.

``starting_no`` and ``session`` are optional because some flag messages
apply to a sector rather than a specific car and the server omits the
``SESSION`` key in those frames.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class RaceMessage:
    """PID 3: race-control message (pit, flag, penalty, info)."""

    event_pid: ClassVar[int] = 3

    text: str
    category: str
    starting_no: int | None = None
    session: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)
