"""Tests for Transport Protocol + ClockOffset + ReconnectPolicy.

These tests verify the runtime-checkable Protocol surface and the helper
types declared in :mod:`aionlslivetiming.transport.base`. The
``ReplayTransport`` is used as the real Protocol implementer for the
``isinstance`` checks (the file is imported by ``test_replay_transport``
too, so this creates an honest cross-module dependency).
"""

from __future__ import annotations

import time

import pytest

from aionlslivetiming.transport import (
    ClockOffset,
    LTSNotFoundEvent,
    ReconnectPolicy,
    Transport,
)
from aionlslivetiming.transport.replay import ReplayTransport  # actual implementer


def test_transport_protocol_is_runtime_checkable() -> None:
    """ReplayTransport satisfies Transport at runtime."""
    # ReplayTransport() does no I/O until connect(); constructing is cheap.
    rt = ReplayTransport("/tmp/nonexistent.jsonl")
    assert isinstance(rt, Transport)


def test_transport_protocol_rejects_non_transport() -> None:
    """Plain objects do not satisfy Transport."""
    assert not isinstance(object(), Transport)
    assert not isinstance("not a transport", Transport)
    assert not isinstance(42, Transport)


def test_clock_offset_update_and_now() -> None:
    """ClockOffset.update stores the offset; now_server_ms reflects it."""
    c = ClockOffset()
    assert c.offset_ms is None
    assert c.now_server_ms() is None
    c.update(server_time_ms=1_000_000, local_recv_ms=999_500)
    # offset = 500; now_server_ms ~= local now + 500 (allow ±50ms slack for CI)
    now = c.now_server_ms()
    local_now = int(time.time() * 1000)
    assert now is not None
    assert abs(now - local_now - 500) < 50


def test_clock_offset_ewma_smoothing() -> None:
    """Two updates: second update pulls the offset toward the new sample (0.3 alpha)."""
    c = ClockOffset()
    c.update(1000, 500)  # offset = 500
    c.update(2000, 1500)  # sample = 500; EWMA = 0.7*500 + 0.3*500 = 500
    assert c.offset_ms == pytest.approx(500.0)
    c.update(2000, 1000)  # sample = 1000; EWMA = 0.7*500 + 0.3*1000 = 650
    assert c.offset_ms == pytest.approx(650.0)


def test_reconnect_policy_defaults_match_d09() -> None:
    """ReconnectPolicy field defaults match CONTEXT.md D-09."""
    p = ReconnectPolicy()
    assert p.base_delay_s == 1.0
    assert p.cap_delay_s == 60.0
    assert p.max_attempts is None
    assert p.initial_offset_s == 10.0
    assert p.honor_retry_after is True


def test_lts_not_found_event_is_frozen_dataclass() -> None:
    """LTSNotFoundEvent is frozen; assignment raises."""
    e = LTSNotFoundEvent(reason="not_yet_started", event_id="NLS-1", first_seen_at_ms=1000)
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError is a subclass
        e.reason = "ended"  # type: ignore[misc]


def test_lts_not_found_reasons_are_three() -> None:
    """LTSNotFoundReason is the three-state literal."""
    e1 = LTSNotFoundEvent(reason="not_yet_started", event_id="x", first_seen_at_ms=0)
    e2 = LTSNotFoundEvent(reason="ended", event_id="x", first_seen_at_ms=0)
    e3 = LTSNotFoundEvent(reason="unknown_event", event_id="x", first_seen_at_ms=0)
    assert e1.reason != e2.reason != e3.reason
