"""Transport subpackage (Phase 3)."""

from __future__ import annotations

from aionlslivetiming.exceptions import (
    ConnectionError,
    NLSError,
    NLSHttpFallbackUnavailable,
    ReplayEmptyError,
    ReplayError,
    ReplayOrderingError,
    ReplaySchemaError,
    UnknownEventError,
)
from aionlslivetiming.transport.base import (
    ClockOffset,
    LTSNotFoundEvent,
    LTSNotFoundReason,
    ReconnectPolicy,
    Transport,
)
from aionlslivetiming.transport.recorder import JsonlRecorder
from aionlslivetiming.transport.replay import ReplayTransport
from aionlslivetiming.transport.websocket import LiveTransport, LTSNotFoundPolicy

# Plan 03 will add:
# from aionlslivetiming.transport.recorder import RecordingTransport

__all__ = [
    "ClockOffset",
    "ConnectionError",
    "JsonlRecorder",
    "LTSNotFoundEvent",
    "LTSNotFoundPolicy",
    "LTSNotFoundReason",
    "LiveTransport",
    "NLSError",
    "NLSHttpFallbackUnavailable",
    "ReconnectPolicy",
    "RecordingTransport",  # populated by Plan 03
    "ReplayEmptyError",
    "ReplayError",
    "ReplayOrderingError",
    "ReplaySchemaError",
    "ReplayTransport",
    "Transport",
    "UnknownEventError",
]
