"""D-03 logging contract: WARNING dedupe + per-field emission.

These tests pin the behaviour of :func:`warn_missing`:
- A WARNING is logged exactly once per unique ``(event_pid, field_name)`` pair.
- ``reset_warned()`` (test-only) clears the dedupe set so tests stay independent.
- The dispatcher logs a single WARNING per unknown ``eventPid``.
- ``parse()`` never raises on a missing or malformed field.
"""

from __future__ import annotations

import logging

import pytest

from aionlslivetiming.events import TrackStateMessage, UnknownMessage
from aionlslivetiming.parser import parse
from aionlslivetiming.parser._helpers import reset_warned, warn_missing


def test_warning_logged_once_per_event_pid_field(caplog: logging.LogRecord) -> None:
    """Repeated calls for the same (event_pid, field) pair emit a single WARNING."""
    with caplog.at_level(logging.WARNING, logger="aionlslivetiming.parser"):
        warn_missing("TRACKSTATE", 4)
        warn_missing("TRACKSTATE", 4)
        warn_missing("TRACKSTATE", 4)
    matching = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(matching) == 1, f"expected 1 log record, got {len(matching)}"


def test_warning_logged_for_distinct_field_on_same_pid(caplog: logging.LogRecord) -> None:
    """A different field on the same pid emits a second WARNING."""
    with caplog.at_level(logging.WARNING, logger="aionlslivetiming.parser"):
        warn_missing("TRACKSTATE", 4)
        warn_missing("TIMESTATE", 4)
    matching = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(matching) == 2


def test_warning_logged_for_same_field_on_different_pid(caplog: logging.LogRecord) -> None:
    """The same field on a different pid emits a second WARNING."""
    with caplog.at_level(logging.WARNING, logger="aionlslivetiming.parser"):
        warn_missing("TRACKSTATE", 4)
        warn_missing("TRACKSTATE", 7)
    matching = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(matching) == 2


def test_reset_warned_clears_state(caplog: logging.LogRecord) -> None:
    """``reset_warned()`` (test-only) clears the dedupe set so a second log fires."""
    with caplog.at_level(logging.WARNING, logger="aionlslivetiming.parser"):
        warn_missing("TRACKSTATE", 4)
        reset_warned()
        warn_missing("TRACKSTATE", 4)
    matching = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(matching) == 2


def test_parse_does_not_raise_on_missing_field() -> None:
    """A known-PID frame with a missing required field still parses (D-03)."""
    msg = parse({"eventPid": 4})  # no TRACKSTATE, no TIMESTATE
    assert isinstance(msg, TrackStateMessage)
    assert msg.track_state == ""
    assert msg.time_state == ""


def test_parse_does_not_raise_on_empty_dict() -> None:
    """An empty dict falls through to UnknownMessage (no raise, D-03)."""
    msg = parse({})
    assert isinstance(msg, UnknownMessage)


def test_dispatcher_logs_warning_on_unknown_pid(caplog: logging.LogRecord) -> None:
    """``parse({eventPid: 9999, ...})`` returns UnknownMessage and logs WARNING."""
    with caplog.at_level(logging.WARNING, logger="aionlslivetiming.parser"):
        msg = parse({"eventPid": 9999, "junk": 1})
    assert isinstance(msg, UnknownMessage)
    matching = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(matching) == 1


def test_dispatcher_logs_warning_once_per_unknown_pid(caplog: logging.LogRecord) -> None:
    """Repeated ``parse({eventPid: 9999, ...})`` calls emit a single WARNING (D-03)."""
    with caplog.at_level(logging.WARNING, logger="aionlslivetiming.parser"):
        parse({"eventPid": 9999, "junk": 1})
        parse({"eventPid": 9999, "more": "data"})
    matching = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(matching) == 1, f"expected 1 log record, got {len(matching)}"


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param({}, id="empty-dict"),
        pytest.param({"type": "not-time"}, id="type-not-time-no-eventpid"),
        pytest.param({"eventPid": "junk"}, id="string-eventpid"),
        pytest.param({"eventPid": 4.5}, id="float-eventpid"),
    ],
)
def test_parse_handles_pathological_inputs(raw: dict[str, object]) -> None:
    """``parse`` must never raise on any of these input shapes (D-03)."""
    msg = parse(raw)  # type: ignore[arg-type]
    # Whatever it returns, it must be a Message subclass
    assert msg is not None
