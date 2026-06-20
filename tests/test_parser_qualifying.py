"""PID 501 (qualifying) parser specifics.

Top-qualifying tables: a ``RESULT`` array of CarResult rows. The
qualifying parser does not deal with sectors; each row carries
``startingNo``, ``position``, ``class``, ``driver``, and ``best``.
"""

from __future__ import annotations

from aionlslivetiming.events import QualifyingMessage
from aionlslivetiming.parser.qualifying import parse_pid_501


def test_two_results() -> None:
    """Two-row qualifying result table parses to 2 CarResult entries."""
    raw = {
        "eventPid": 501,
        "RESULT": [
            {
                "startingNo": 7,
                "position": 1,
                "class": "SP9",
                "driver": "M. Müller",
                "best": 148200,
            },
            {
                "startingNo": 11,
                "position": 2,
                "class": "SP9",
                "driver": "F. Schmidt",
                "best": 149100,
            },
        ],
    }
    msg = parse_pid_501(raw)
    assert isinstance(msg, QualifyingMessage)
    assert len(msg.results) == 2
    assert msg.results[0].driver == "M. Müller"
    assert msg.results[0].best_lap_ms == 148200
    assert msg.results[1].position == 2


def test_no_result() -> None:
    """A frame without ``RESULT`` parses to an empty tuple (D-03)."""
    msg = parse_pid_501({})
    assert msg.results == ()


def test_partial_result_row() -> None:
    """A row missing some optional fields still parses (D-03)."""
    raw = {
        "eventPid": 501,
        "RESULT": [{"startingNo": 7, "position": 1}],
    }
    msg = parse_pid_501(raw)
    assert len(msg.results) == 1
    assert msg.results[0].starting_no == 7
    assert msg.results[0].position == 1
    assert msg.results[0].class_name is None
    assert msg.results[0].driver is None
    assert msg.results[0].best_lap_ms is None
