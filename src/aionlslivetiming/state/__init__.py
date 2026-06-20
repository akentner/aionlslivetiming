"""In-memory race state cache.

Public surface: :class:`RaceState` (the reducer) plus the read-side
value types :class:`CarState`, :class:`TrackState`, :class:`LapRecord`
and the two lifecycle enums :class:`Source` / :class:`Freshness`.

The :class:`RaceState` is the only object consumers normally need to
hold — ``state.apply(msg)`` reduces a :class:`~aionlslivetiming.events.Message`
into the cache, and ``state.cars`` / ``state.laps(no)`` / ``state.standings()``
read from it.
"""

from __future__ import annotations

from aionlslivetiming.state.car import CarState
from aionlslivetiming.state.enums import Freshness, Source
from aionlslivetiming.state.lap import LapRecord
from aionlslivetiming.state.race_state import RaceState
from aionlslivetiming.state.track import TrackState

__all__ = [
    "CarState",
    "Freshness",
    "LapRecord",
    "RaceState",
    "Source",
    "TrackState",
]
