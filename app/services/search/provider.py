import base64
import hashlib
import json
from urllib.parse import quote_plus, urlparse
from xml.etree import ElementTree

import httpx
from pydantic import HttpUrl, TypeAdapter
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.core.exceptions import SearchError, SearchRateLimitError, SearchTimeoutError
from app.domain.search import SearchResult
from app.services.http import create_http_client, post_with_retries


class YandexSearchProvider:
    """Yandex Search API v2 adapter returning provider-independent search results."""

    def __init__(self, config: Settings, cache: Redis | None = None) -> None:
        self._config = config
        self._cache = cache

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self._config.yandex_api_key or not self._config.yandex_folder_id:
            raise SearchError("Search provider is not configured")
        normalized_query = " ".join(query.casefold().split())
        cache_key = (
            "cache:v1:search:"
            f"{hashlib.sha256(f'{quote_plus(normalized_query)}:{limit}'.encode()).hexdigest()}"
        )
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return [SearchResult.model_validate(item) for item in cached]
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Api-Key {self._config.yandex_api_key}",
        }
        payload = {
            "query": {
                "searchType": self._config.yandex_search_type,
                "queryText": query,
                "familyMode": self._config.yandex_family_mode,
                "page": "0",
            },
            "folderId": self._config.yandex_folder_id,
            "responseFormat": self._config.yandex_response_format,
            "groupSpec": {
                "groupMode": "GROUP_MODE_FLAT",
                "groupsOnPage": str(limit),
                "docsInGroup": "1",
            },
            "maxPassages": str(min(5, max(1, limit))),
        }
        try:
            async with create_http_client(
                self._config,
                self._config.search_timeout,
                proxy_url=self._config.search_proxy_url or None,
                inherit_config_proxy=False,
            ) as client:
                response = await post_with_retries(
                    client,
                    self._config.yandex_api_url,
                    json=payload,
                    headers=headers,
                    config=self._config,
                )
        except httpx.TimeoutException as exc:
            raise SearchTimeoutError("Search request timed out") from exc
        except httpx.HTTPError as exc:
            raise SearchError("Search request failed") from exc
        if response.status_code == 429:
            raise SearchRateLimitError("Search provider rate limit reached")
        if response.status_code >= 400:
            raise SearchError("Search provider returned an error")
        try:
            response_data = response.json()
            raw_data = response_data.get("rawData")
            if not isinstance(raw_data, str):
                raise ValueError("rawData is missing")
            xml_data = base64.b64decode(raw_data, validate=True)
            results = self._parse_xml(xml_data, limit)
        except (AttributeError, KeyError, TypeError, ValueError, ElementTree.ParseError) as exc:
            raise SearchError("Search provider returned malformed data") from exc
        await self._set_cached(cache_key, results)
        return results

    @staticmethod
    def _parse_xml(xml_data: bytes, limit: int) -> list[SearchResult]:
        root = ElementTree.fromstring(xml_data)
        results: list[SearchResult] = []
        for element in root.iter():
            if YandexSearchProvider._local_name(element.tag) != "doc":
                continue
            url = YandexSearchProvider._descendant_text(element, {"url", "link"})
            if not url or urlparse(url).scheme not in {"http", "https"}:
                continue
            title = YandexSearchProvider._descendant_text(element, {"title", "name"})
            snippet = YandexSearchProvider._descendant_text(
                element, {"passage", "passages", "snippet", "description"}
            )
            hostname = urlparse(url).hostname
            if not hostname:
                continue
            results.append(
                SearchResult(
                    title=title or url,
                    url=TypeAdapter(HttpUrl).validate_python(url),
                    snippet=snippet or "",
                    domain=hostname,
                    relevance_score=max(0.1, 1 - len(results) / max(limit, 1) * 0.5),
                    metadata={"provider": "yandex"},
                )
            )
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    @staticmethod
    def _descendant_text(element: ElementTree.Element, names: set[str]) -> str:
        for child in element.iter():
            if YandexSearchProvider._local_name(child.tag) in names:
                text = " ".join("".join(child.itertext()).split())
                if text:
                    return text
        return ""

    async def _get_cached(self, key: str) -> list[dict[str, object]] | None:
        if self._cache is None:
            return None
        try:
            value = await self._cache.get(key)
        except RedisError:
            return None
        return json.loads(value) if value else None

    async def _set_cached(self, key: str, results: list[SearchResult]) -> None:
        if self._cache is None:
            return
        try:
            await self._cache.setex(
                key,
                self._config.search_cache_ttl,
                json.dumps([item.model_dump(mode="json") for item in results]),
            )
        except RedisError:
            return


class UnconfiguredSearchProvider:
    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        del query, limit
        raise SearchError("Search provider is not configured")


# Backward-compatible import for code that used the generic provider name.
HttpSearchProvider = YandexSearchProvider
