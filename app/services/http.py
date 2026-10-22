import asyncio
from collections.abc import Mapping

import httpx

from app.config import Settings


def create_http_client(
    config: Settings,
    timeout: float,
    *,
    proxy_url: str | None = None,
    inherit_config_proxy: bool = True,
) -> httpx.AsyncClient:
    """Create an outbound client with an optional explicit proxy policy."""
    if inherit_config_proxy:
        proxy_url = proxy_url or config.external_proxy_url or config.tg_proxy_url
    return httpx.AsyncClient(timeout=timeout, proxy=proxy_url or None)


async def post_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: Mapping[str, str],
    json: object,
    config: Settings,
) -> httpx.Response:
    """Retry only transient transport, throttling and 5xx failures."""
    for attempt in range(config.external_max_retries + 1):
        try:
            response = await client.post(url, headers=headers, json=json)
        except (httpx.TimeoutException, httpx.ConnectError):
            if attempt >= config.external_max_retries:
                raise
        else:
            if response.status_code not in {429, 500, 502, 503, 504}:
                return response
            if attempt >= config.external_max_retries:
                return response
        await asyncio.sleep(config.external_backoff_seconds * (2**attempt))
    raise RuntimeError("retry loop exhausted")
