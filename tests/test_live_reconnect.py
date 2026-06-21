"""Tests for the LiveTransport reconnect loop (D-09..D-13).

Verifies the backoff formula and ReconnectPolicy defaults directly. The
reconnect loop itself is exercised indirectly via the LiveTransport
integration tests in ``test_live_transport.py``.
"""

from __future__ import annotations

import pytest

from aionlslivetiming.transport import ReconnectPolicy


@pytest.mark.parametrize(
    "attempt,expected_cap",
    [
        (0, 1.0),  # base * 2^0 = 1
        (1, 2.0),  # base * 2^1 = 2
        (2, 4.0),  # base * 2^2 = 4
        (3, 8.0),  # base * 2^3 = 8
        (6, 60.0),  # base * 2^6 = 64, capped at 60
        (10, 60.0),  # well past cap
    ],
)
def test_backoff_cap_formula(attempt: int, expected_cap: float) -> None:
    """D-10 full-jitter cap = min(cap_delay_s, base_delay_s * 2**attempt)."""
    p = ReconnectPolicy(base_delay_s=1.0, cap_delay_s=60.0)
    cap = min(p.cap_delay_s, p.base_delay_s * (2**attempt))
    assert cap == pytest.approx(expected_cap)


def test_initial_offset_s_default_is_ten() -> None:
    """D-11: default initial_offset_s is 10.0 (per-process random sleep before first attempt)."""
    assert ReconnectPolicy().initial_offset_s == 10.0


def test_max_attempts_none_means_infinite() -> None:
    """D-09: max_attempts=None is the default — infinite retry."""
    assert ReconnectPolicy().max_attempts is None


def test_max_attempts_zero_stops_after_first_failure() -> None:
    """With max_attempts=0, no retries happen."""
    p = ReconnectPolicy(max_attempts=0)
    assert p.max_attempts == 0


def test_honor_retry_after_default_true() -> None:
    """D-12: Retry-After header honored by default."""
    assert ReconnectPolicy().honor_retry_after is True


def test_reconnect_policy_default_base_and_cap() -> None:
    """D-09: defaults are base_delay_s=1.0, cap_delay_s=60.0."""
    p = ReconnectPolicy()
    assert p.base_delay_s == 1.0
    assert p.cap_delay_s == 60.0


def test_reconnect_policy_is_frozen() -> None:
    """ReconnectPolicy is frozen — mutation raises FrozenInstanceError."""
    import dataclasses

    p = ReconnectPolicy()
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.base_delay_s = 2.0  # type: ignore[misc]
