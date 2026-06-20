"""Time-sync parser (no PID branch — type-discriminated)."""

from __future__ import annotations

from aionlslivetiming.events import TimeSyncMessage
from aionlslivetiming.parser import parse
from aionlslivetiming.parser.time_sync import parse_time_sync


def test_time_sync_value() -> None:
    """``{type:'time', value:ms}`` → TimeSyncMessage with value_ms set."""
    msg = parse_time_sync({"type": "time", "value": 1700000000000})
    assert isinstance(msg, TimeSyncMessage)
    assert msg.value_ms == 1700000000000
    assert msg.event_pid == -1


def test_time_sync_dispatch_does_not_enter_pid_branch() -> None:
    """The dispatcher matches ``type=='time'`` BEFORE any eventPid lookup.

    A frame with both ``type:'time'`` and an ``eventPid`` that would
    otherwise match a known channel still routes to TimeSyncMessage.
    The sentinel event_pid=-1 is part of the contract: a consumer that
    reads ``msg.event_pid`` knows it received a time-sync frame even
    without inspecting the raw payload.
    """
    raw = {"type": "time", "value": 12345, "eventPid": 4}
    msg = parse(raw)
    assert isinstance(msg, TimeSyncMessage)
    assert msg.event_pid == -1
    assert msg.value_ms == 12345


def test_time_sync_raw_preserved() -> None:
    """The raw ``{type, value}`` dict is preserved verbatim (PARSE-03)."""
    raw = {"type": "time", "value": 99, "extra": "keep-me"}
    msg = parse_time_sync(raw)
    assert msg.raw["extra"] == "keep-me"


def test_time_sync_empty_value() -> None:
    """An empty ``value`` parses to 0 (D-03)."""
    msg = parse_time_sync({"type": "time"})
    assert msg.value_ms == 0


def test_time_sync_malformed_value() -> None:
    """A non-numeric ``value`` falls back to 0 (D-03)."""
    msg = parse_time_sync({"type": "time", "value": "junk"})
    assert msg.value_ms == 0
