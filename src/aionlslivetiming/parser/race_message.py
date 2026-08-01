"""Parser for PID 3 (race messages).

Maps the NLS server's PID 3 payload (``text``, ``type``, ``startingNo``,
``session``) onto :class:`RaceMessage`. ``type`` is mapped to the
``category`` field; ``session`` is the race session id (e.g. ``"R1"``).

.. note::

   The SPA leaderboard also renders a per-car "State" column with short
   codes (``PI``, ``F``, ``I1``-``I4``). Those are **not** PID 3
   ``type`` values; they are attached to the car, not the track, and
   live on a different field (likely PID 7 per-car or an unmodelled
   PID). See ``.planning/research/PER_CAR_STATE_CODES.md`` for the
   unverified mapping and a verification plan.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aionlslivetiming.events.race_message import RaceMessage
from aionlslivetiming.parser._helpers import _opt_int, _opt_str, warn_missing

__all__ = ["parse_pid_3"]

_EVENT_PID = 3


def parse_pid_3(raw: Mapping[str, Any]) -> RaceMessage:
    """Parse a PID 3 payload into a :class:`RaceMessage`.

    The server wraps each race-control message in a ``MESSAGES`` list
    with the actual text in ``MESSAGES[0].MESSAGE`` and category in
    ``MESSAGES[0].MESSAGEGROUP``. Top-level ``text``/``type`` fields
    are also accepted for forward-compat with older / alternative
    server payloads.
    """
    messages = raw.get("MESSAGES") or []
    first = messages[0] if isinstance(messages, list) and messages else None

    if first is None and "text" not in raw:
        warn_missing("text", _EVENT_PID)
    if first is None and "type" not in raw:
        warn_missing("type", _EVENT_PID)

    if first is not None:
        text = str(first.get("MESSAGE", ""))
        category = str(first.get("MESSAGEGROUP", "") or "INFO")
        starting_no = _opt_int(first.get("STARTING_NO") or first.get("startingNo"))
        session = _opt_str(first.get("SESSION") or first.get("session"))
    else:
        text = str(raw.get("text", ""))
        category = str(raw.get("type", "INFO"))
        starting_no = _opt_int(raw.get("startingNo"))
        session = _opt_str(raw.get("session"))

    return RaceMessage(
        text=text,
        category=category,
        starting_no=starting_no,
        session=session,
        raw=dict(raw),
    )
