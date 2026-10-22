import httpx
import pytest

from app.config import Settings
from app.domain.enums import ContentStatus
from app.domain.schemas import Source
from app.domain.search import AuthorityLevel, SourceType
from app.services.extraction.url import UrlContentExtractor
from app.services.http import post_with_retries
from app.services.queue import CheckJobQueue
from app.services.ratelimit import RateLimiter
from app.services.search.normalizer import SourceNormalizer
from app.services.search.service import SourceSearchService


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self.redis = redis

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def incr(self, key: str) -> None:
        self.redis.values[key] = self.redis.values.get(key, 0) + 1

    async def expire(self, key: str, seconds: int, nx: bool = False) -> None:
        self.redis.expiry[key] = seconds

    async def execute(self) -> list[int]:
        return [next(reversed(self.redis.values.values())), 1]


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.expiry: dict[str, int] = {}

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        del transaction
        return FakePipeline(self)


@pytest.mark.asyncio
async def test_rate_limiter_is_per_user_and_has_ttl() -> None:
    redis = FakeRedis()
    limiter = RateLimiter(redis, limit=1, window_seconds=60)

    assert await limiter.allow(1, "check") is True
    assert await limiter.allow(1, "check") is False
    assert await limiter.allow(2, "check") is True
    assert next(iter(redis.expiry.values())) == 60


class FakeQueueRedis:
    def __init__(self) -> None:
        self.items: list[tuple[str, dict[str, str]]] = []

    async def xgroup_create(self, *args: object, **kwargs: object) -> None:
        return None

    async def xautoclaim(self, *args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        return ["0-0", []]

    async def xadd(self, stream: str, fields: dict[str, str]) -> str:
        del stream
        message_id = str(len(self.items) + 1)
        self.items.append((message_id, fields))
        return message_id

    async def xreadgroup(
        self, *args: object, **kwargs: object
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        del args, kwargs
        return [("stream", [self.items.pop(0)])]

    async def xack(self, *args: object) -> int:
        del args
        return 1


@pytest.mark.asyncio
async def test_redis_queue_round_trip() -> None:
    redis = FakeQueueRedis()
    queue = CheckJobQueue(redis, stream="jobs", group="workers")  # type: ignore[arg-type]

    message_id = await queue.enqueue({"check_id": 7, "attempt": 0})
    received = await queue.receive("worker-1", 10)
    await queue.acknowledge(message_id)

    assert received == (message_id, {"check_id": 7, "attempt": 0})


@pytest.mark.asyncio
async def test_external_retry_retries_transient_500() -> None:
    statuses = iter([500, 200])

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(next(statuses))

    config = Settings(external_max_retries=1, external_backoff_seconds=0)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await post_with_retries(
            client,
            "https://example.com",
            headers={},
            json={},
            config=config,
        )

    assert response.status_code == 200


def test_url_cache_key_normalizes_tracking_parameters() -> None:
    first = UrlContentExtractor._cache_key("https://Example.com/article/?utm_source=x&b=2&a=1")
    second = UrlContentExtractor._cache_key("https://example.com/article?a=1&b=2")
    assert first == second


def test_search_deduplicates_same_document_across_urls() -> None:
    service = SourceSearchService.__new__(SourceSearchService)
    service._normalizer = SourceNormalizer()
    source_one = Source(
        source_id="one",
        title="Clinical guidance on walking",
        url="https://official.example/first",
        domain="official.example",
        source_type=SourceType.GUIDELINE,
        authority_level=AuthorityLevel.HIGH,
        content_status=ContentStatus.NOT_FETCHED,
    )
    source_two = source_one.model_copy(
        update={"source_id": "two", "url": "https://mirror.example/copy"}
    )

    result = SourceSearchService._deduplicate(service, [source_one, source_two])

    assert len(result) == 1
