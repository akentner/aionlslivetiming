"""State lifecycle enums.

Two stdlib enums driving the ``RaceState`` lifecycle:

- :class:`Source` — where the messages came from. Drives the
  ``state.source`` surface and the default for ``RaceState(source=...)``.
- :class:`Freshness` — how up-to-date the cache is. ``FRESH`` is the
  steady state after any ``apply()``; ``STALE`` is reserved for future
  staleness policies (e.g. time-based expiry); ``RESYNCING`` is the
  initial state and the post-``clear()`` state.
"""

from __future__ import annotations

from enum import Enum


class Source(Enum):
    """Origin of the messages fed into a :class:`~aionlslivetiming.state.RaceState`.

    - ``LIVE`` — connected to a running race via WebSocket.
    - ``REPLAY`` — driven from a recorded JSONL log.
    - ``IMPORTED`` — loaded from a JSON snapshot via the persistence API.
    """

    LIVE = "LIVE"
    REPLAY = "REPLAY"
    IMPORTED = "IMPORTED"


class Freshness(Enum):
    """Cache-staleness state machine.

    - ``RESYNCING`` — no data applied yet, or :meth:`RaceState.clear`
      was just called. Consumers should treat the cache as empty.
    - ``FRESH`` — at least one ``apply()`` has succeeded and the cache
      reflects the messages seen so far.
    - ``STALE`` — reserved for a future staleness policy (e.g. age-based
      expiry). Not set by the current :class:`RaceState` but exported
      so downstream code can switch on the full set.
    """

    RESYNCING = "RESYNCING"
    FRESH = "FRESH"
    STALE = "STALE"
