from typing import cast

from redis.asyncio import Redis, from_url

from app.config import settings


def create_redis() -> Redis:
    """Create the shared Redis client for future cache, limits and queues."""
    client = from_url(  # type: ignore[no-untyped-call]
        settings.redis_url, decode_responses=True
    )
    return cast(Redis, client)
