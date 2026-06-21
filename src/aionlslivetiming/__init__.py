"""AIO NLS Livetiming API.

Async-first Python client for the official Nürburgring Langstrecken-Serie
livetiming service at ``livetiming.azurewebsites.net``.
"""

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
from aionlslivetiming.logging import get_logger
from aionlslivetiming.state import Filter, Freshness, RaceState, Source
from aionlslivetiming.transport import (
    ClockOffset,
    JsonlRecorder,
    LiveTransport,
    LTSNotFoundEvent,
    LTSNotFoundPolicy,
    ReconnectPolicy,
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
    "LTSNotFoundEvent",
    "LTSNotFoundPolicy",
    "LiveTransport",
    "NLSError",
    "NLSHttpFallbackUnavailable",
    "RaceState",
    "ReconnectPolicy",
    "ReplayEmptyError",
    "ReplayError",
    "ReplayOrderingError",
    "ReplaySchemaError",
    "ReplayTransport",
    "Source",
    "Transport",
    "UnknownEventError",
    "__version__",
    "get_logger",
]
