"""Parser subpackage.

The parser is a pure-function layer that turns raw ``dict`` payloads
received from the WebSocket into typed :data:`Message` values. It performs
no I/O, no async, and no transport. The ``parse()`` dispatcher lands in
Plan 03; this Phase 1 stub only re-exports the channel ID constants so
importers can ``from aionlslivetiming.parser import EVENT_PID_RESULT`` and
similar.
"""

from aionlslivetiming.parser.channels import (
    EVENT_PID_PER_CAR_LAPS,
    EVENT_PID_QUALIFYING,
    EVENT_PID_RACE_MESSAGE,
    EVENT_PID_RESULT,
    EVENT_PID_STATISTICS,
    EVENT_PID_TRACK_STATE,
)

__all__ = [
    "EVENT_PID_PER_CAR_LAPS",
    "EVENT_PID_QUALIFYING",
    "EVENT_PID_RACE_MESSAGE",
    "EVENT_PID_RESULT",
    "EVENT_PID_STATISTICS",
    "EVENT_PID_TRACK_STATE",
]
