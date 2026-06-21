"""AIO NLS Livetiming API.

Async-first Python client for the official Nürburgring Langstrecken-Serie
livetiming service at ``livetiming.azurewebsites.net``.
"""

from aionlslivetiming.client import NLSClient
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
from aionlslivetiming.http import fetch_laps_data
from aionlslivetiming.logging import get_logger
from aionlslivetiming.state import Filter, Freshness, RaceState, Source
from aionlslivetiming.transport import (
    ClockOffset,
    JsonlRecorder,
    LiveTransport,
    LTSNotFoundEvent,
    LTSNotFoundPolicy,
    ReconnectPolicy,
    RecordingTransport,
    ReplayTransport,
    Transport,
)
from aionlslivetiming.version import __version__

__all__ = [
    "ClockOffset",
    "ConnectionError",
    "Filter",
    "Freshness",
    "JsonlRecorder",
    "LTSNotFoundError",
    "LTSNotFoundEvent",
    "LTSNotFoundPolicy",
    "LiveTransport",
    "NLSClient",
    "NLSError",
    "NLSHttpFallbackUnavailable",
    "ParseError",
    "RaceState",
    "ReconnectPolicy",
    "RecordingTransport",
    "ReplayEmptyError",
    "ReplayError",
    "ReplayOrderingError",
    "ReplaySchemaError",
    "ReplayTransport",
    "Source",
    "Transport",
    "UnknownEventError",
    "__version__",
    "fetch_laps_data",
    "get_logger",
]
