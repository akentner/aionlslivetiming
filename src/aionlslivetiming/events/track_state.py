"""Track-state message (PID 4).

PID 4 frames report the live race-control state: ``TRACKSTATE`` (green
flag, yellow flag, chequered, safety car, …), ``TIMESTATE`` (running,
paused, finished) and the current race clock (``TOD``) plus, when
the race finishes, the final ``ENDTIME``.

``track_state`` and ``time_state`` are kept as plain ``str`` rather than
an enum — the server is not versioned and a closed enum would force a
code change every time a new flag is introduced (PROJECT.md pitfall:
"schema can change between seasons"). Downstream code that wants to
switch on them should compare against the documented literals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping

    from aionlslivetiming.events.common import TimeOfDay


@dataclass(frozen=True, slots=True)
class TrackStateMessage:
    """PID 4: live race-control state (track flag + time state)."""

    event_pid: ClassVar[int] = 4

    track_state: str
    time_state: str
    tod: TimeOfDay | None = None
    end_time: TimeOfDay | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)
