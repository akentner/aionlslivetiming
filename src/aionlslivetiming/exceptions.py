"""NLS exception hierarchy (preliminary; D-EXC).

Layered exception types so consumers can `except NLSError` for everything
or narrow to specific kinds. Names are preliminary and may move to a
dedicated subpackage at Phase 4 (NLSClient composition root).
"""

from __future__ import annotations


class NLSError(Exception):
    """Base class for all aionlslivetiming exceptions."""


class ConnectionError(NLSError):
    """WebSocket transport-level connection failure (after retry exhaustion)."""


class UnknownEventError(NLSError):
    """LTS_NOT_FOUND classified as `unknown_event` (D-07 not_yet_started/ended silent)."""


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
    """`ts_recv_ms` is not monotonically non-decreasing across consecutive lines.

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
    "NLSError",
    "NLSHttpFallbackUnavailable",
    "ReplayEmptyError",
    "ReplayError",
    "ReplayOrderingError",
    "ReplaySchemaError",
    "UnknownEventError",
]
