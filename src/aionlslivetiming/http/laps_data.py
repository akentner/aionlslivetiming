"""Optional HTTP laps-data fallback.

The primary per-car-lap data source is the WebSocket channel 7 subscription
(``PER_CAR_LAPS``). The server also exposes an ``/event/{id}/laps-data``
endpoint that some consumers prefer for drilldown. As documented in
PROJECT.md, that endpoint returns an HTML SPA in many cases — this
function detects that and raises :class:`NLSHttpFallbackUnavailable`
with a clear "use channel 7 instead" message.

HA compatibility (STACK.md WebSession Injection): accept an injected
``httpx.AsyncClient``. Integration consumers pass their shared async
client (e.g. HA's ``create_async_httpx_client(hass)``) to share the
integration's connection pool. Library code without an injected client
creates its own short-lived client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aionlslivetiming.exceptions import NLSHttpFallbackUnavailable
from aionlslivetiming.logging import get_logger

if TYPE_CHECKING:
    import httpx


_log = get_logger("aionlslivetiming.http.laps_data")

# Server URL pattern — matches the JS bundle's factory for the laps-data drilldown.
# Configurable per consumer; default is the live server.
DEFAULT_LAPS_DATA_BASE_URL: str = "https://livetiming.azurewebsites.net"


def _build_url(base_url: str, event_id: str, session: str | None, starting_no: int | None) -> str:
    """Compose the laps-data URL. Trailing slashes are stripped."""
    base = base_url.rstrip("/")
    url = f"{base}/event/{event_id}/laps-data"
    params: list[str] = []
    if session is not None:
        params.append(f"session={session}")
    if starting_no is not None:
        params.append(f"startingNo={starting_no}")
    if params:
        url += "?" + "&".join(params)
    return url


async def fetch_laps_data(
    event_id: str,
    *,
    session: str | None = None,
    starting_no: int | None = None,
    base_url: str = DEFAULT_LAPS_DATA_BASE_URL,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Fetch the /event/{id}/laps-data endpoint.

    Parameters
    ----------
    event_id:
        Event identifier (e.g. ``"NLS-1"``).
    session:
        Optional session filter (``"R1"``, ``"Q1"``, etc.).
    starting_no:
        Optional starting number filter.
    base_url:
        Base URL for the livetiming service (defaults to production).
    client:
        Optional pre-configured ``httpx.AsyncClient``. If ``None``, a
        short-lived client is created for this call. HA integrations
        should inject the shared client from the framework's helpers
        (see STACK.md WebSession Injection rule).

    Returns
    -------
    dict
        Parsed JSON response.

    Raises
    ------
    NLSHttpFallbackUnavailable
        When the server returns non-JSON (HTML SPA), or Content-Type
        indicates HTML/text. The error message tells the consumer to
        use channel 7 instead.
    """
    import httpx

    url = _build_url(base_url, event_id, session, starting_no)
    _log.info("fetching laps-data from %s", url)

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    assert client is not None  # narrow for mypy -- we just created it if None
    try:
        response = await client.get(url)
        # Inspect Content-Type BEFORE parsing — HTML response is the failure mode
        content_type = response.headers.get("content-type", "").lower()
        if "html" in content_type or "text/" in content_type:
            raise NLSHttpFallbackUnavailable(
                f"laps-data endpoint returned {content_type!r} "
                f"(likely the SPA shell). Subscribe to channel 7 instead."
            )
        # Try to parse as JSON; raise if it fails (server returned something else)
        try:
            data = response.json()
        except Exception as exc:
            raise NLSHttpFallbackUnavailable(
                f"laps-data endpoint returned non-JSON body: {exc}. Subscribe to channel 7 instead."
            ) from exc
        if not isinstance(data, dict):
            raise NLSHttpFallbackUnavailable(
                f"laps-data endpoint returned JSON but not an object "
                f"(got {type(data).__name__}). Subscribe to channel 7 instead."
            )
        return data
    finally:
        if owns_client:
            await client.aclose()


__all__ = ["DEFAULT_LAPS_DATA_BASE_URL", "fetch_laps_data"]
