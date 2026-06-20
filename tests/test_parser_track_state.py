"""PID 4 (track state) parser specifics.

Covers the TRACKSTATE/TIMESTATE/TOD/ENDTIME combinations: running
(with TOD), finished (with ENDTIME), and minimal/empty (both None).
"""

from __future__ import annotations

from aionlslivetiming.events import TrackStateMessage
from aionlslivetiming.parser.track_state import parse_pid_4


def test_running_state() -> None:
    """A running race has TRACKSTATE=green, TIMESTATE=running, TOD set."""
    raw = {"eventPid": 4, "TRACKSTATE": "GREEN", "TIMESTATE": "RUNNING", "TOD": {"value": 1834000}}
    msg = parse_pid_4(raw)
    assert isinstance(msg, TrackStateMessage)
    assert msg.track_state == "GREEN"
    assert msg.time_state == "RUNNING"
    assert msg.tod is not None
    assert msg.tod.value_ms == 1834000
    assert msg.end_time is None


def test_finished_state() -> None:
    """A finished race has TRACKSTATE=chequered, TIMESTATE=finished, ENDTIME set."""
    raw = {
        "eventPid": 4,
        "TRACKSTATE": "CHEQUERED",
        "TIMESTATE": "FINISHED",
        "ENDTIME": {"value": 7200000},
    }
    msg = parse_pid_4(raw)
    assert msg.track_state == "CHEQUERED"
    assert msg.time_state == "FINISHED"
    assert msg.end_time is not None
    assert msg.end_time.value_ms == 7200000
    assert msg.tod is None


def test_minimal_state() -> None:
    """An empty dict parses to track_state='', time_state='', both TOD and ENDTIME None."""
    msg = parse_pid_4({})
    assert msg.track_state == ""
    assert msg.time_state == ""
    assert msg.tod is None
    assert msg.end_time is None


def test_unknown_field_preserved() -> None:
    """Unknown server fields are preserved in ``raw`` (PARSE-03)."""
    raw = {
        "eventPid": 4,
        "TRACKSTATE": "GREEN",
        "TIMESTATE": "RUNNING",
        "futureFlag": "value",
    }
    msg = parse_pid_4(raw)
    assert msg.raw["futureFlag"] == "value"


def test_tod_malformed_does_not_raise() -> None:
    """A TOD payload that is not a Mapping falls back to None (D-03)."""
    raw = {"eventPid": 4, "TRACKSTATE": "GREEN", "TIMESTATE": "RUNNING", "TOD": "broken"}
    msg = parse_pid_4(raw)
    assert msg.tod is None
    assert msg.track_state == "GREEN"
