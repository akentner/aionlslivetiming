"""Typed event messages emitted by the parser.

Each ``Message`` is a frozen :func:`dataclasses.dataclass` (D-01: stdlib
only, no pydantic on this layer). The parser (Plan 03) maps raw
WebSocket frames onto these types; the state cache (Phase 2) consumes
them.

Every concrete message carries an ``event_pid: ClassVar[int]`` so the
parser dispatcher can route by ``eventPid`` without importing every
class. ``UnknownMessage`` is the forward-compatibility fallback —
emitted for any PID the parser does not recognise so the feed never
crashes when the server's schema changes between seasons.

The public :data:`Message` union aliases the eight concrete types and
is what the consumer-facing API will accept and yield.
"""

from __future__ import annotations

from typing import Union

from aionlslivetiming.events.common import BestSector, CarResult, SessionInfo, TimeOfDay
from aionlslivetiming.events.initial_state import InitialStateMessage
from aionlslivetiming.events.per_car_laps import PerCarLapsMessage
from aionlslivetiming.events.qualifying import QualifyingMessage
from aionlslivetiming.events.race_message import RaceMessage
from aionlslivetiming.events.statistics import StatisticsMessage
from aionlslivetiming.events.time_sync import TimeSyncMessage
from aionlslivetiming.events.track_state import TrackStateMessage
from aionlslivetiming.events.unknown import UnknownMessage

# Explicit ``Union[...]`` alias is the public API contract (D-06) — the
# ``Union[`` token is part of the key_link grep pattern documented in the
# 01-02 plan, so we keep the explicit ``typing.Union`` form rather than
# rewriting as ``X | Y | Z`` even though PEP 604 would otherwise apply.
Message = Union[  # noqa: UP007
    InitialStateMessage,
    TrackStateMessage,
    RaceMessage,
    PerCarLapsMessage,
    QualifyingMessage,
    StatisticsMessage,
    TimeSyncMessage,
    UnknownMessage,
]

__all__ = [
    "BestSector",
    "CarResult",
    "InitialStateMessage",
    "Message",
    "PerCarLapsMessage",
    "QualifyingMessage",
    "RaceMessage",
    "SessionInfo",
    "StatisticsMessage",
    "TimeOfDay",
    "TimeSyncMessage",
    "TrackStateMessage",
    "UnknownMessage",
]
