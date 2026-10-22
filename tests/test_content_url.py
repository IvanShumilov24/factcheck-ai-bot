import httpx
import pytest

from app.config import Settings
from app.core.exceptions import CaptchaDetectedError, ContentTooLargeError, UrlFetchError
from app.domain.content import ContentInput, ContentType
from app.services.extraction.url import UrlContentExtractor


class FakeClient:
    def __init__(self, response: httpx.Response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def stream(self, method: str, url: str, follow_redirects: bool = False):
        del method, url, follow_redirects
        return FakeStream(self.response)


class FakeStream:
    def __init__(self, response: httpx.Response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *args):
        return None

    async def aiter_bytes(self):
        yield self.response.content


def public_dns(monkeypatch) -> None:
    monkeypatch.setattr(
        "socket.getaddrinfo", lambda *args: [(None, None, None, None, ("93.184.216.34", 0))]
    )


@pytest.mark.asyncio
async def test_url_extracts_html_and_title(monkeypatch) -> None:
    public_dns(monkeypatch)
    response = httpx.Response(
        200,
        content=(
            b"<html><head><title>Title</title></head><body>"
            b"<script>x</script>Hello medical text</body></html>"
        ),
        headers={"content-type": "text/html"},
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient(response))
    result = await UrlContentExtractor(Settings()).extract(
        ContentInput(source_type=ContentType.URL, url="https://example.com/article")
    )
    assert result.title == "Title"
    assert result.extracted_text == "Title Hello medical text"


@pytest.mark.asyncio
async def test_localhost_is_blocked() -> None:
    with pytest.raises(UrlFetchError):
        await UrlContentExtractor(Settings()).extract(
            ContentInput(source_type=ContentType.URL, url="http://localhost/private")
        )


@pytest.mark.asyncio
async def test_private_ip_is_blocked(monkeypatch) -> None:
    monkeypatch.setattr(
        "socket.getaddrinfo", lambda *args: [(None, None, None, None, ("192.168.1.10", 0))]
    )
    with pytest.raises(UrlFetchError):
        await UrlContentExtractor(Settings()).extract(
            ContentInput(source_type=ContentType.URL, url="https://example.com")
        )


@pytest.mark.asyncio
async def test_download_limit_is_enforced(monkeypatch) -> None:
    public_dns(monkeypatch)
    response = httpx.Response(200, content=b"12345", headers={"content-type": "text/html"})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient(response))
    with pytest.raises(ContentTooLargeError):
        await UrlContentExtractor(Settings(MAX_DOWNLOAD_SIZE=4)).extract(
            ContentInput(source_type=ContentType.URL, url="https://example.com")
        )


@pytest.mark.asyncio
async def test_captcha_page_is_not_treated_as_content(monkeypatch) -> None:
    public_dns(monkeypatch)
    response = httpx.Response(
        200,
        content=(
            b"<html><title>Checking your browser</title><body>Verify you are human</body></html>"
        ),
        headers={"content-type": "text/html"},
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient(response))
    with pytest.raises(CaptchaDetectedError):
        await UrlContentExtractor(Settings()).extract(
            ContentInput(source_type=ContentType.URL, url="https://example.com/article")
        )
