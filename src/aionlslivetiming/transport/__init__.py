"""Transport subpackage (Phase 3)."""

from __future__ import annotations

from aionlslivetiming.exceptions import (
    ConnectionError,
    LTSNotFoundError,
    NLSError,
    NLSHttpFallbackUnavailable,
    ParseError,
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
from aionlslivetiming.transport.recorder_wrapper import RecordingTransport
from aionlslivetiming.transport.replay import ReplayTransport
from aionlslivetiming.transport.websocket import LiveTransport, LTSNotFoundPolicy

__all__ = [
    "ClockOffset",
    "ConnectionError",
    "JsonlRecorder",
    "LTSNotFoundError",
    "LTSNotFoundEvent",
    "LTSNotFoundPolicy",
    "LTSNotFoundReason",
    "LiveTransport",
    "NLSError",
    "NLSHttpFallbackUnavailable",
    "ParseError",
    "ReconnectPolicy",
    "RecordingTransport",
    "ReplayEmptyError",
    "ReplayError",
    "ReplayOrderingError",
    "ReplaySchemaError",
    "ReplayTransport",
    "Transport",
    "UnknownEventError",
]
