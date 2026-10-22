import hashlib
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, redis: Redis, *, limit: int, window_seconds: int) -> None:
        self._redis = redis
        self._limit = limit
        self._window = window_seconds

    async def allow(self, user_id: int, operation: str) -> bool:
        safe_user = hashlib.sha256(str(user_id).encode()).hexdigest()[:16]
        key = f"ratelimit:v1:{operation}:{safe_user}"
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                await pipe.incr(key)
                await pipe.expire(key, self._window, nx=True)
                values = await pipe.execute()
            return int(values[0]) <= self._limit
        except RedisError:
            logger.warning("rate_limit_redis_unavailable operation=%s", operation)
            return True
