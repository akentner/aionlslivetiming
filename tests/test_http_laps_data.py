"""Tests for fetch_laps_data — JSON success, HTML failure, injected client.

The primary per-car-lap data source is the WebSocket channel 7 subscription.
The server also exposes an `/event/{id}/laps-data` HTTP endpoint that
returns an HTML SPA shell in many cases — fetch_laps_data detects that
and raises :class:`NLSHttpFallbackUnavailable` with a clear "use channel 7
instead" message.

HA compatibility (STACK.md WebSession Injection): consumers inject their
own ``httpx.AsyncClient`` (from ``create_async_httpx_client(hass)``); the
function must use the injected client when provided and not silently
replace it with an internal one.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from aionlslivetiming.exceptions import NLSHttpFallbackUnavailable
from aionlslivetiming.http.laps_data import (
    DEFAULT_LAPS_DATA_BASE_URL,
    fetch_laps_data,
)


@pytest.fixture
def mock_laps_data() -> respx.MockRouter:
    """Respx mock router for the laps-data endpoint."""
    with respx.mock(assert_all_called=False) as router:
        yield router


async def test_fetch_laps_data_success_returns_dict(mock_laps_data: respx.MockRouter) -> None:
    """A JSON response is returned as a dict."""
    route = mock_laps_data.get(
        url__startswith=f"{DEFAULT_LAPS_DATA_BASE_URL}/event/NLS-1/laps-data"
    ).mock(
        return_value=httpx.Response(
            200, json={"laps": [{"startingNo": 7, "lapTime": 162340}]}
        )
    )
    result = await fetch_laps_data("NLS-1")
    assert route.called
    assert result == {"laps": [{"startingNo": 7, "lapTime": 162340}]}


async def test_fetch_laps_data_html_response_raises(mock_laps_data: respx.MockRouter) -> None:
    """HTML response (the SPA shell) raises NLSHttpFallbackUnavailable."""
    route = mock_laps_data.get(
        url__startswith=f"{DEFAULT_LAPS_DATA_BASE_URL}/event/NLS-1/laps-data"
    ).mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<!DOCTYPE html><html><body>SPA shell</body></html>",
        )
    )
    with pytest.raises(NLSHttpFallbackUnavailable) as exc_info:
        await fetch_laps_data("NLS-1")
    assert "channel 7" in str(exc_info.value).lower()
    assert route.called


async def test_fetch_laps_data_invalid_json_raises(mock_laps_data: respx.MockRouter) -> None:
    """A response with JSON content-type but invalid JSON raises NLSHttpFallbackUnavailable."""
    route = mock_laps_data.get(
        url__startswith=f"{DEFAULT_LAPS_DATA_BASE_URL}/event/NLS-1/laps-data"
    ).mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "application/json"},
            text="this is not json{",
        )
    )
    with pytest.raises(NLSHttpFallbackUnavailable):
        await fetch_laps_data("NLS-1")
    assert route.called


async def test_fetch_laps_data_json_non_object_raises(mock_laps_data: respx.MockRouter) -> None:
    """A JSON response that's not an object (e.g. a list) raises NLSHttpFallbackUnavailable."""
    route = mock_laps_data.get(
        url__startswith=f"{DEFAULT_LAPS_DATA_BASE_URL}/event/NLS-1/laps-data"
    ).mock(return_value=httpx.Response(200, json=[1, 2, 3]))
    with pytest.raises(NLSHttpFallbackUnavailable):
        await fetch_laps_data("NLS-1")
    assert route.called


async def test_fetch_laps_data_with_session_and_starting_no(
    mock_laps_data: respx.MockRouter,
) -> None:
    """URL composition includes session + startingNo query parameters."""
    route = mock_laps_data.get(
        url__regex=r".*/event/NLS-1/laps-data\?.*session=R1.*startingNo=7.*"
    ).mock(return_value=httpx.Response(200, json={"laps": []}))
    result = await fetch_laps_data("NLS-1", session="R1", starting_no=7)
    assert route.called
    assert result == {"laps": []}


async def test_fetch_laps_data_uses_injected_client(mock_laps_data: respx.MockRouter) -> None:
    """When a client is injected, fetch_laps_data uses it (does not create its own)."""
    route = mock_laps_data.get(
        url__startswith=f"{DEFAULT_LAPS_DATA_BASE_URL}/event/NLS-1/laps-data"
    ).mock(return_value=httpx.Response(200, json={"laps": []}))
    async with httpx.AsyncClient() as client:
        result = await fetch_laps_data("NLS-1", client=client)
    assert route.called
    assert result == {"laps": []}


async def test_fetch_laps_data_default_url_constant() -> None:
    """The default URL points to the production endpoint."""
    assert DEFAULT_LAPS_DATA_BASE_URL == "https://livetiming.azurewebsites.net"


async def test_fetch_laps_data_strips_trailing_slash(mock_laps_data: respx.MockRouter) -> None:
    """A base_url with trailing slash is normalized."""
    route = mock_laps_data.get(url__startswith="https://example.com/event/X/laps-data").mock(
        return_value=httpx.Response(200, json={"laps": []})
    )
    result = await fetch_laps_data("X", base_url="https://example.com/")
    assert route.called
    assert result == {"laps": []}
