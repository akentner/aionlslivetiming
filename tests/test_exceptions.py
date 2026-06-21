"""Tests for the NLS exception hierarchy (preliminary, per D-EXC).

Per D-EXC the exception names are preliminary and may move to a dedicated
subpackage at Phase 4 (NLSClient composition root). The hierarchy is the
load-bearing contract: every concrete error must be catchable as `NLSError`.
"""

from __future__ import annotations

from aionlslivetiming import (
    ConnectionError,
    NLSError,
    NLSHttpFallbackUnavailable,
    ReplayEmptyError,
    ReplayError,
    ReplayOrderingError,
    ReplaySchemaError,
    UnknownEventError,
)


def test_nls_error_is_base() -> None:
    """All NLS exceptions subclass NLSError."""
    assert issubclass(ConnectionError, NLSError)
    assert issubclass(UnknownEventError, NLSError)
    assert issubclass(ReplayError, NLSError)
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
    """`except NLSError` catches every concrete subclass."""
    # Per-class constructors: most take just a message; ReplaySchemaError
    # needs a line_no; ReplayOrderingError needs (line_no, prev_ts, curr_ts).
    cases: list[tuple[type[NLSError], tuple[object, ...]]] = [
        (ConnectionError, ("test",)),
        (UnknownEventError, ("test",)),
        (ReplayEmptyError, ("test",)),
        (ReplaySchemaError, (1,)),
        (ReplayOrderingError, (1, 1000, 500)),
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
