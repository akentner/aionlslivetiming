"""Unknown-PID parser specifics (D-04 forward-compat)."""

from __future__ import annotations

import logging

from aionlslivetiming.events import UnknownMessage
from aionlslivetiming.parser.unknown import parse_unknown


def test_unknown_pid_returns_unknown_message() -> None:
    """``parse_unknown(raw, pid)`` returns an UnknownMessage with event_pid set."""
    raw = {"junk": 1, "futureServerField": "data"}
    msg = parse_unknown(raw, 9999)
    assert isinstance(msg, UnknownMessage)
    assert msg.event_pid == 9999
    # raw payload preserved
    assert msg.raw["junk"] == 1
    assert msg.raw["futureServerField"] == "data"


def test_unknown_pid_logs_warning(caplog: logging.LogRecord) -> None:
    """``parse_unknown`` does not log; the dispatcher does.

    The WARN-on-unknown-PID contract lives at the dispatcher level
    (D-04). ``parse_unknown`` itself is the pure construction leaf.
    """
    with caplog.at_level(logging.WARNING, logger="aionlslivetiming.parser"):
        msg = parse_unknown({}, 8888)
    assert msg.event_pid == 8888
    # ``parse_unknown`` should not log; the dispatcher does
    assert all(r.name != "aionlslivetiming.parser" for r in caplog.records)
