from base64 import b64encode

import httpx
import pytest

from app.config import Settings
from app.core.exceptions import SearchError, SearchRateLimitError
from app.services.search.provider import YandexSearchProvider

XML_RESPONSE = b"""
<yandexsearch>
  <response><results><grouping>
    <group><doc>
      <url>https://www.who.int/news-room/fact-sheets/detail/healthy-diet</url>
      <title>Healthy diet</title>
      <passages><passage>A healthy diet helps protect against disease.</passage></passages>
    </doc></group>
  </grouping></results></response>
</yandexsearch>
"""


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict[str, object] | None = None):
        self.status_code = status_code
        self._payload = payload or {"rawData": b64encode(XML_RESPONSE).decode()}

    def json(self) -> dict[str, object]:
        return self._payload


class FakeAsyncClient:
    response = FakeResponse()
    request: dict[str, object] = {}

    def __init__(self, **kwargs: object):
        self.kwargs = kwargs

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.request = {"url": url, **kwargs}
        FakeAsyncClient.request = self.request
        return self.response


@pytest.mark.asyncio
async def test_yandex_provider_posts_api_key_and_parses_xml(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    provider = YandexSearchProvider(
        Settings(
            YANDEX_API_KEY="secret",
            YANDEX_FOLDER_ID="folder",
        )
    )

    results = await provider.search("vitamin D", limit=3)

    assert len(results) == 1
    assert results[0].title == "Healthy diet"
    assert str(results[0].url) == "https://www.who.int/news-room/fact-sheets/detail/healthy-diet"
    assert results[0].domain == "www.who.int"
    assert "healthy diet" in results[0].snippet
    assert FakeAsyncClient.request["url"] == "https://searchapi.api.cloud.yandex.net/v2/web/search"
    assert FakeAsyncClient.request["headers"]["authorization"] == "Api-Key secret"
    assert FakeAsyncClient.request["json"]["folderId"] == "folder"
    assert FakeAsyncClient.request["json"]["query"]["queryText"] == "vitamin D"


@pytest.mark.asyncio
async def test_yandex_provider_maps_rate_limit(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    FakeAsyncClient.response = FakeResponse(status_code=429)
    provider = YandexSearchProvider(Settings(YANDEX_API_KEY="key", YANDEX_FOLDER_ID="folder"))

    with pytest.raises(SearchRateLimitError):
        await provider.search("query")

    FakeAsyncClient.response = FakeResponse()


@pytest.mark.asyncio
async def test_yandex_provider_rejects_malformed_response(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    FakeAsyncClient.response = FakeResponse(payload={"rawData": "not-base64"})
    provider = YandexSearchProvider(Settings(YANDEX_API_KEY="key", YANDEX_FOLDER_ID="folder"))

    with pytest.raises(SearchError, match="malformed"):
        await provider.search("query")

    FakeAsyncClient.response = FakeResponse()
