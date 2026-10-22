import hashlib
import ipaddress
import json
import socket
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from pydantic import HttpUrl, TypeAdapter
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.core.exceptions import (
    CaptchaDetectedError,
    ContentTooLargeError,
    EmptyContentError,
    ExtractionError,
    UnsupportedContentError,
    UrlFetchError,
)
from app.domain.content import ContentInput, ContentType, ExtractedContent
from app.services.http import create_http_client


class UrlContentExtractor:
    def __init__(self, config: Settings, cache: Redis | None = None) -> None:
        self._config = config
        self._cache = cache

    async def extract(self, content: ContentInput) -> ExtractedContent:
        if content.source_type is not ContentType.URL or content.url is None:
            raise UrlFetchError("URL content is required")
        url = str(content.url)
        self._validate_url(url)
        cached = await self._get_cached(url)
        if cached is not None:
            return ExtractedContent.model_validate(cached)

        current_url = url
        async with create_http_client(self._config, self._config.request_timeout) as client:
            for _ in range(self._config.max_redirects + 1):
                self._validate_url(current_url)
                try:
                    async with client.stream(
                        "GET", current_url, follow_redirects=False
                    ) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise UrlFetchError("Redirect has no destination")
                            current_url = urljoin(current_url, location)
                            continue
                        if response.status_code >= 400:
                            raise UrlFetchError("Remote page returned an error")
                        content_length = response.headers.get("content-length")
                        if content_length and int(content_length) > self._config.max_download_size:
                            raise ContentTooLargeError(
                                "Downloaded page exceeds the configured limit"
                            )
                        chunks: list[bytes] = []
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > self._config.max_download_size:
                                raise ContentTooLargeError(
                                    "Downloaded page exceeds the configured limit"
                                )
                            chunks.append(chunk)
                        body = b"".join(chunks)
                        result = self._parse_html(current_url, response, body)
                except httpx.HTTPError as exc:
                    raise UrlFetchError("Unable to fetch URL") from exc
                await self._set_cached(url, result)
                return result
        raise UrlFetchError("Too many redirects")

    def _validate_url(self, value: str) -> None:
        if len(value) > self._config.max_url_length:
            raise ContentTooLargeError("URL exceeds the configured limit")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise UrlFetchError("Only HTTP and HTTPS URLs are supported")
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname in {"localhost", "localhost.localdomain"}:
            raise UrlFetchError("Local destinations are not allowed")
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
        except socket.gaierror as exc:
            raise UrlFetchError("URL host cannot be resolved") from exc
        if any(self._is_private_address(str(address)) for address in addresses):
            raise UrlFetchError("Private network destinations are not allowed")

    @staticmethod
    def _is_private_address(value: str) -> bool:
        address = ipaddress.ip_address(value)
        return bool(
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        )

    def _parse_html(self, url: str, response: httpx.Response, body: bytes) -> ExtractedContent:
        try:
            content_type = response.headers.get("content-type", "").casefold()
            if content_type and not any(
                item in content_type for item in ("text/html", "application/xhtml+xml")
            ):
                raise UnsupportedContentError("Only HTML sources are supported")
            soup = BeautifulSoup(body, "html.parser")
            raw_text = " ".join(soup.get_text(" ").split())
            marker_text = raw_text.casefold()
            captcha_markers = (
                "captcha",
                "recaptcha",
                "checking your browser",
                "verify you are human",
                "security verification",
                "anti-bot challenge",
            )
            if any(marker in marker_text for marker in captcha_markers):
                raise CaptchaDetectedError("Source returned an anti-bot challenge")
            for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
                tag.decompose()
            title_tag = soup.find("title")
            canonical_tag = soup.find("link", rel="canonical")
            text = " ".join(soup.get_text(" ").split())
            if not text:
                raise EmptyContentError("HTML page contains no extractable text")
            title_text = title_tag.get_text(" ").strip() if title_tag else ""
            if title_text and text.casefold() == title_text.casefold():
                raise EmptyContentError("HTML page contains no substantive content")
            metadata_markers = sum(
                marker in text.casefold()
                for marker in ("authors", "journal", "doi", "pmid", "affiliations")
            )
            if (
                len(text) < 600
                and metadata_markers >= 2
                and not any(punctuation in text for punctuation in (".", "?", "!"))
            ):
                raise EmptyContentError("HTML page contains bibliographic metadata only")
            canonical = canonical_tag.get("href") if canonical_tag else None
            source_url = urljoin(url, str(canonical)) if canonical else url
            return ExtractedContent(
                source_type=ContentType.URL,
                original_reference=url,
                extracted_text=text,
                title=title_tag.get_text(strip=True) if title_tag else None,
                source_url=TypeAdapter(HttpUrl).validate_python(source_url),
                extraction_method="beautifulsoup_html",
                metadata={"content_type": response.headers.get("content-type", "")},
            )
        except (ExtractionError, UnsupportedContentError, EmptyContentError, CaptchaDetectedError):
            raise
        except Exception as exc:
            raise ExtractionError("Unable to extract page text") from exc

    async def _get_cached(self, url: str) -> dict[str, object] | None:
        if self._cache is None:
            return None
        try:
            key = self._cache_key(url)
            value = await self._cache.get(key)
        except RedisError:
            return None
        return json.loads(value) if value else None

    async def _set_cached(self, url: str, content: ExtractedContent) -> None:
        if self._cache is not None:
            try:
                key = self._cache_key(url)
                await self._cache.setex(
                    key, self._config.content_cache_ttl, content.model_dump_json()
                )
            except RedisError:
                return

    @staticmethod
    def _cache_key(url: str) -> str:
        parsed = urlparse(url)
        query = sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query)
            if not key.casefold().startswith("utm_")
        )
        canonical = urlunparse(
            (
                parsed.scheme.casefold(),
                parsed.netloc.casefold(),
                parsed.path.rstrip("/") or "/",
                "",
                urlencode(query),
                "",
            )
        )
        return f"cache:v1:content:{hashlib.sha256(canonical.encode()).hexdigest()}"
