"""Time-sync message (``{"type": "time", "value": <ms>}``).

The NLS server's first WebSocket frame is a time-sync ping
(``{"type": "time", "value": <ms>}``) used by the client to measure
round-trip latency. It is *not* a PID-discriminated event — the
parser detects it on the ``type`` field rather than ``eventPid``.

``event_pid`` is set to ``-1`` (a sentinel that no real NLS PID
matches) so the parser dispatcher's ``eventPid`` lookup naturally
falls through to the ``type``-based branch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class TimeSyncMessage:
    """``{"type": "time", "value": <ms>}`` server time-sync ping."""

    event_pid: ClassVar[int] = -1

    value_ms: int
    raw: Mapping[str, Any] = field(default_factory=dict)
