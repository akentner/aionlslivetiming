"""Parser subpackage — public ``parse()`` dispatcher.

The parser is a pure-function layer that turns raw ``dict`` payloads
received from the WebSocket into typed :data:`Message` values. It
performs no I/O, no async, and no transport.

The :func:`parse` function is the single entry point used by every
transport (Phase 3) and the state cache (Phase 2). It dispatches on
the raw ``type`` field (for the time-sync frame) and on ``eventPid``
(for the 6 known channels) to return the matching typed ``Message``.
Unknown PIDs return :class:`UnknownMessage` (forward-compat) and log
a single WARNING line.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aionlslivetiming.events import Message
from aionlslivetiming.parser._helpers import warn_missing
from aionlslivetiming.parser.channels import (
    EVENT_PID_PER_CAR_LAPS,
    EVENT_PID_QUALIFYING,
    EVENT_PID_RACE_MESSAGE,
    EVENT_PID_RESULT,
    EVENT_PID_STATISTICS,
    EVENT_PID_TRACK_STATE,
)
from aionlslivetiming.parser.initial_state import parse_pid_0
from aionlslivetiming.parser.per_car_laps import parse_pid_7
from aionlslivetiming.parser.qualifying import parse_pid_501
from aionlslivetiming.parser.race_message import parse_pid_3
from aionlslivetiming.parser.statistics import parse_pid_9002
from aionlslivetiming.parser.time_sync import parse_time_sync
from aionlslivetiming.parser.track_state import parse_pid_4
from aionlslivetiming.parser.unknown import parse_unknown

__all__ = [
    "EVENT_PID_PER_CAR_LAPS",
    "EVENT_PID_QUALIFYING",
    "EVENT_PID_RACE_MESSAGE",
    "EVENT_PID_RESULT",
    "EVENT_PID_STATISTICS",
    "EVENT_PID_TRACK_STATE",
    "parse",
]


def parse(raw: Mapping[str, Any]) -> Message:
    """Dispatch a raw server frame onto the matching typed ``Message``.

    D-05: the ``{"type": "time", "value": <ms>}`` time-sync frame is
    matched *first*, before any ``eventPid`` lookup, so it never
    enters the race-message stream.

    D-06: a ``match/case`` over the 6 known PIDs selects the leaf
    parser; the catch-all returns :class:`UnknownMessage` and logs a
    single WARNING via the shared dedupe set.

    D-03: never raises on a known-PID / missing-field / malformed
    payload — each leaf constructs the ``Message`` with optional
    fields defaulting to ``None`` / ``()`` instead.
    """
    if raw.get("type") == "time":
        return parse_time_sync(raw)

    pid = raw.get("eventPid")
    # Some PID 0 frames (notably the LTS_NOT_FOUND lazy initial state)
    # omit the ``eventPid`` discriminator but still set ``PID == 0`` in
    # the short-code payload. Fall back to ``PID`` so those frames
    # still hit the initial-state parser instead of UnknownMessage.
    if pid is None and raw.get("PID") == 0:
        pid = 0
    match pid:
        case 0:
            return parse_pid_0(raw)
        case 3:
            return parse_pid_3(raw)
        case 4:
            return parse_pid_4(raw)
        case 7:
            return parse_pid_7(raw)
        case 501:
            return parse_pid_501(raw)
        case 9002:
            return parse_pid_9002(raw)
        case _:
            # D-04: unknown PID — return UnknownMessage, log WARNING
            # exactly once per process per unknown PID.
            pid_int = int(pid) if isinstance(pid, int) else -1
            warn_missing(f"unknown_eventPid:{pid_int}", pid_int)
            return parse_unknown(raw, pid_int)
