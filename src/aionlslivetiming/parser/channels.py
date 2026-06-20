"""Stable channel (eventPid) ID constants for the multiplexed NLS WebSocket.

The NLS livetiming server publishes a single WebSocket stream in which
payloads are tagged with an integer ``eventPid`` field selecting one of the
following channels. The values are taken from reverse-engineering of the
production JavaScript bundle (``leaderboard.e24a.bundle.js`` etc.) and have
been stable across observed server versions.

The constants are re-exported from :mod:`aionlslivetiming.parser` so callers
can write ``from aionlslivetiming.parser import EVENT_PID_RESULT``.
"""

from __future__ import annotations

__all__ = [
    "EVENT_PID_PER_CAR_LAPS",
    "EVENT_PID_QUALIFYING",
    "EVENT_PID_RACE_MESSAGE",
    "EVENT_PID_RESULT",
    "EVENT_PID_STATISTICS",
    "EVENT_PID_TRACK_STATE",
]

#: Initial results payload and ongoing race-position updates.
#: Carries the per-car lap counts, sector times, gaps, and positions.
EVENT_PID_RESULT: int = 0

#: Race-control message channel.
#: Pit stops, flags, penalties, sector bests and other timing notices.
EVENT_PID_RACE_MESSAGE: int = 3

#: Track-state updates.
#: Carries ``TRACKSTATE`` (e.g. ``"GREEN"``), ``TIMESTATE`` and ``ENDTIME``.
EVENT_PID_TRACK_STATE: int = 4

#: Per-car lap drilldown channel.
#: Subscribed with ``{"session": ..., "startingNo": ...}`` handshake
#: parameters; the server emits per-lap data for the requested car.
EVENT_PID_PER_CAR_LAPS: int = 7

#: Top qualifying (pro / pro-am tables).
EVENT_PID_QUALIFYING: int = 501

#: Statistics channel.
#: Leading laps, best laps and best sectors summary.
EVENT_PID_STATISTICS: int = 9002
