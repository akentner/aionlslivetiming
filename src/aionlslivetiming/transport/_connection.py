"""Per-connection bookkeeping for LiveTransport.

Not part of the public API. Tracks last-frame time (idle watchdog),
track-state history (LTS_NOT_FOUND ``ended`` classifier), and the first
LTS_NOT_FOUND timestamp (for the ``first_seen_at_ms`` field).

This module is intentionally tiny and dependency-free so the watchdog
timer logic stays trivially correct.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# TrackState values that mean the race is over (D-06 / TRACKSTATE field).
# The server sends ``CHEQUERED`` at the moment the leading car crosses
# the finish line; ``FINISHED`` arrives after the full field has stopped
# recording laps. Both are terminal for live consumption.
_ENDED_TRACK_STATES: frozenset[str] = frozenset({"FINISHED", "CHEQUERED"})


@dataclass
class _ConnectionState:
    """Mutable per-connection state owned by :class:`LiveTransport`.

    A fresh instance is created for each session (i.e., each successful
    connect+handshake), so cross-session state from a previous race
    cannot leak in. The ``ended_seen`` and ``seen_initial_state_with_results``
    flags feed the D-06 LTS_NOT_FOUND classifier.
    """

    event_id: str
    connected_at_s: float = field(default_factory=time.monotonic)
    last_frame_at_s: float = field(default_factory=time.monotonic)
    seen_initial_state_with_results: bool = False
    ended_seen: bool = False  # a TrackState with FINISHED/CHEQUERED, or non-empty end_time
    first_lts_not_found_at_ms: int | None = None

    def record_frame(self) -> None:
        """Update ``last_frame_at_s``; called on every received frame (including time-sync)."""
        self.last_frame_at_s = time.monotonic()

    def observe_track_state(self, track_state: str | None, end_time: object | None) -> None:
        """Update ``ended_seen`` based on a TrackStateMessage.

        ``track_state`` is the ``TRACKSTATE`` field (string) and
        ``end_time`` is the ``ENDTIME`` value (or ``None``). A non-empty
        ``ENDTIME`` is also a sign that the race is over, even if the
        server has not yet emitted ``TRACKSTATE=FINISHED``.
        """
        if track_state in _ENDED_TRACK_STATES:
            self.ended_seen = True
        elif end_time:
            # ``ENDTIME`` is a TimeOfDay (string) — truthy when set.
            self.ended_seen = True

    def observe_initial_state(self, has_results: bool) -> None:
        """Update ``seen_initial_state_with_results`` (PID 0 with non-empty RESULT)."""
        if has_results:
            self.seen_initial_state_with_results = True

    def idle_seconds(self) -> float:
        """Seconds since the last frame (D-02 watchdog)."""
        return time.monotonic() - self.last_frame_at_s

    def connection_age_seconds(self) -> float:
        """Seconds since connect() (D-06 not_yet_started heuristic)."""
        return time.monotonic() - self.connected_at_s


__all__ = ["_ConnectionState"]
