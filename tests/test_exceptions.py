"""Tests for the NLS exception hierarchy (per D-23).

Names are finalized at Phase 4. The hierarchy is the load-bearing contract:
every concrete error must be catchable as ``NLSError``.
"""

from __future__ import annotations

from aionlslivetiming import (
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
from aionlslivetiming import __all__ as _package_all
from aionlslivetiming.exceptions import __all__ as _exceptions_all


def test_nls_error_is_base() -> None:
    """All NLS exceptions subclass NLSError."""
    assert issubclass(ConnectionError, NLSError)
    assert issubclass(LTSNotFoundError, NLSError)
    assert issubclass(UnknownEventError, NLSError)
    assert issubclass(ReplayError, NLSError)
    assert issubclass(ParseError, NLSError)
    assert issubclass(NLSHttpFallbackUnavailable, NLSError)


def test_replay_subclasses_inherit_replay_error() -> None:
    """ReplayError is the base; its subclasses share the hierarchy."""
    assert issubclass(ReplayEmptyError, ReplayError)
    assert issubclass(ReplaySchemaError, ReplayError)
    assert issubclass(ReplayOrderingError, ReplayError)


def test_replay_schema_error_carries_line_no() -> None:
    """ReplaySchemaError exposes line_no as an attribute."""
    e = ReplaySchemaError(line_no=42)
    assert e.line_no == 42
    assert "42" in str(e)


def test_replay_ordering_error_carries_prev_and_curr() -> None:
    """ReplayOrderingError exposes prev_ts and curr_ts."""
    e = ReplayOrderingError(line_no=10, prev_ts=1000, curr_ts=500)
    assert e.line_no == 10
    assert e.prev_ts == 1000
    assert e.curr_ts == 500
    assert "1000" in str(e) and "500" in str(e)


def test_all_nls_errors_catchable_as_nls_error() -> None:
    """``except NLSError`` catches every concrete subclass."""
    # Per-class constructors.
    cases: list[tuple[type[NLSError], tuple[object, ...]]] = [
        (ConnectionError, ("test",)),
        (LTSNotFoundError, ("unknown_event", "evt-1")),
        (UnknownEventError, ("test",)),
        (ReplayEmptyError, ("test",)),
        (ReplaySchemaError, (1,)),
        (ReplayOrderingError, (1, 1000, 500)),
        (ParseError, (4, 12, "bad field")),
        (NLSHttpFallbackUnavailable, ("test",)),
    ]
    for cls, args in cases:
        try:
            raise cls(*args)  # type: ignore[arg-type]
        except NLSError as e:
            assert isinstance(e, cls)


def test_replay_schema_error_default_message() -> None:
    """ReplaySchemaError builds a useful default message from line_no."""
    e = ReplaySchemaError(line_no=7)
    assert "line 7" in str(e)


def test_replay_schema_error_custom_message() -> None:
    """ReplaySchemaError respects a custom message override."""
    e = ReplaySchemaError(line_no=7, message="missing raw field")
    assert "missing raw field" in str(e)
    assert e.line_no == 7


# ---- New in Phase 4 (D-23, D-24) ----


def test_lts_not_found_error_carries_reason() -> None:
    """LTSNotFoundError stores the reason as an attribute (D-23)."""
    e = LTSNotFoundError(reason="unknown_event", event_id="evt-1")
    assert e.reason == "unknown_event"
    assert e.event_id == "evt-1"
    assert "unknown_event" in str(e)
    assert "evt-1" in str(e)


def test_lts_not_found_error_is_nls_error() -> None:
    """LTSNotFoundError subclasses NLSError (D-23)."""
    assert issubclass(LTSNotFoundError, NLSError)


def test_lts_not_found_error_event_id_optional() -> None:
    """LTSNotFoundError works without an event_id."""
    e = LTSNotFoundError(reason="ended")
    assert e.reason == "ended"
    assert e.event_id is None
    assert "ended" in str(e)


def test_parse_error_carries_pid_line_message() -> None:
    """ParseError stores event_pid, line_no, and message (D-23)."""
    e = ParseError(event_pid=4, line_no=12, message="bad field")
    assert e.event_pid == 4
    assert e.line_no == 12
    assert "bad field" in str(e)
    assert "12" in str(e)


def test_parse_error_is_nls_error() -> None:
    """ParseError subclasses NLSError."""
    assert issubclass(ParseError, NLSError)


def test_parse_error_handles_none_line_no() -> None:
    """ParseError tolerates line_no=None (no JSONL line context)."""
    e = ParseError(event_pid=7, line_no=None, message="x")
    assert e.line_no is None
    assert "x" in str(e)


def test_unknown_event_error_docstring_documented_as_strict() -> None:
    """UnknownEventError docstring mentions ``--strict`` (D-23 re-purpose)."""
    assert UnknownEventError.__doc__ is not None
    assert "--strict" in UnknownEventError.__doc__


def test_exports_match_all() -> None:
    """Both exceptions ``__all__`` and the package ``__all__`` include the two new names."""
    assert len(_exceptions_all) == 10
    assert "LTSNotFoundError" in _exceptions_all
    assert "ParseError" in _exceptions_all
    assert "UnknownEventError" in _exceptions_all  # re-purposed, not removed
    assert "LTSNotFoundError" in _package_all
    assert "ParseError" in _package_all


def test_unknown_event_error_still_constructible() -> None:
    """UnknownEventError still exists and is constructible (D-23 re-purpose)."""
    e = UnknownEventError("test message")
    assert isinstance(e, NLSError)
    assert "test message" in str(e)
