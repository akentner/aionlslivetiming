"""NLS exception hierarchy.

Layered exception types so consumers can ``except NLSError`` for everything
or narrow to specific kinds. Names are finalized in Phase 4 (D-23):

- :class:`NLSError` — base
- :class:`ConnectionError` — WebSocket transport-level failure (after retry exhaustion)
- :class:`LTSNotFoundError` — LTS_NOT_FOUND classified as ``unknown_event`` (raised
  by :class:`~aionlslivetiming.transport.websocket.LiveTransport` per D-24)
- :class:`UnknownEventError` — repurpose: raised by the CLI ``--strict`` mode
  when an :class:`~aionlslivetiming.events.UnknownMessage` is observed on the
  parsed stream. Distinct from :class:`LTSNotFoundError`.
- :class:`ReplayError` — base for JSONL replay errors
- :class:`ParseError` — raised by the CLI ``--strict`` mode when a parsed
  :class:`~aionlslivetiming.events.Message` violates the parser's strict contract
- :class:`NLSHttpFallbackUnavailable` — ``/event/{id}/laps-data`` HTTP fallback
  returned non-JSON or HTML
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aionlslivetiming.transport.base import LTSNotFoundReason


class NLSError(Exception):
    """Base class for all aionlslivetiming exceptions."""


class ConnectionError(NLSError):
    """WebSocket transport-level connection failure (after retry exhaustion)."""


class LTSNotFoundError(NLSError):
    """Raised by :class:`~aionlslivetiming.transport.websocket.LiveTransport`
    when ``LTS_NOT_FOUND`` is classified as ``unknown_event`` AND the
    :class:`~aionlslivetiming.transport.websocket.LTSNotFoundPolicy.on_unknown_event == 'raise'``.

    Carries the reason and (when available) the event_id for diagnostics.
    Note: :class:`~aionlslivetiming.transport.base.LTSNotFoundEvent` (the typed
    event yielded by ``client.lts_not_found()``) is the soft, observable form;
    this exception is the loud, raised form.

    Attributes:
        reason: One of ``'not_yet_started'``, ``'ended'``, ``'unknown_event'``.
        event_id: The event id whose lookup failed (when known).
    """

    def __init__(
        self,
        reason: LTSNotFoundReason | str,
        event_id: str | None = None,
        message: str | None = None,
    ) -> None:
        self.reason = reason
        self.event_id = event_id
        if message is None:
            if event_id is not None:
                message = f"LTS_NOT_FOUND for event {event_id!r} classified as {reason!r}"
            else:
                message = f"LTS_NOT_FOUND classified as {reason!r}"
        super().__init__(message)


class UnknownEventError(NLSError):
    """Raised by the CLI ``--strict`` mode when an
    :class:`~aionlslivetiming.events.UnknownMessage` is observed on the parsed
    stream. Distinct from :class:`LTSNotFoundError` which signals an invalid
    event id; this exception signals unknown-but-parseable server payload.
    """


class ParseError(NLSError):
    """Raised by the CLI ``--strict`` mode when a parsed
    :class:`~aionlslivetiming.events.Message` violates the parser's strict
    contract. NOT raised by :func:`~aionlslivetiming.parser.parse` itself
    (which is tolerant by default per Phase 1 D-03); only raised by consumer
    code that opts into strict parsing.

    Attributes:
        event_pid: The ``eventPid`` of the offending message.
        line_no: 1-indexed line number in the JSONL replay log, when known.
        message: Human-readable description of the violation.
    """

    def __init__(self, event_pid: int, line_no: int | None, message: str) -> None:
        self.event_pid = int(event_pid)
        self.line_no = line_no
        if line_no is not None:
            full = f"parse error at line {line_no} (event_pid={event_pid}): {message}"
        else:
            full = f"parse error (event_pid={event_pid}): {message}"
        super().__init__(full)


class ReplayError(NLSError):
    """Base for JSONL replay errors."""


class ReplayEmptyError(ReplayError):
    """The replay JSONL is empty."""


class ReplaySchemaError(ReplayError):
    """A line in the replay JSONL is missing required fields.

    Attributes:
        line_no: 1-indexed line number where the violation was detected.
    """

    def __init__(self, line_no: int, message: str | None = None) -> None:
        self.line_no = line_no
        super().__init__(message or f"replay schema error at line {line_no}")


class ReplayOrderingError(ReplayError):
    """``ts_recv_ms`` is not monotonically non-decreasing across consecutive lines.

    A non-monotonic JSONL means the recorder upstream had a bug; this is loud
    on purpose (Pitfall #10 / D-17).

    Attributes:
        line_no: 1-indexed line number of the offending line.
        prev_ts: ts_recv_ms of the previous line.
        curr_ts: ts_recv_ms of the offending line.
    """

    def __init__(self, line_no: int, prev_ts: int, curr_ts: int) -> None:
        self.line_no = line_no
        self.prev_ts = prev_ts
        self.curr_ts = curr_ts
        super().__init__(
            f"replay ts_recv_ms not monotonic at line {line_no}: "
            f"prev={prev_ts} curr={curr_ts}"
        )


class NLSHttpFallbackUnavailable(NLSError):
    """The /event/{id}/laps-data HTTP fallback returned non-JSON or HTML."""


__all__ = [
    "ConnectionError",
    "LTSNotFoundError",
    "NLSError",
    "NLSHttpFallbackUnavailable",
    "ParseError",
    "ReplayEmptyError",
    "ReplayError",
    "ReplayOrderingError",
    "ReplaySchemaError",
    "UnknownEventError",
]
