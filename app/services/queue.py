import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError


class CheckJobQueue:
    """Small Redis Streams queue with explicit acknowledgement."""

    def __init__(self, redis: Redis, *, stream: str, group: str) -> None:
        self._redis = redis
        self._stream = stream
        self._group = group
        self._pending_checked = False

    async def ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def enqueue(self, payload: dict[str, Any]) -> str:
        return str(await self._redis.xadd(self._stream, {"payload": json.dumps(payload)}))

    async def receive(self, consumer: str, block_ms: int) -> tuple[str, dict[str, Any]] | None:
        await self.ensure_group()
        if not self._pending_checked:
            self._pending_checked = True
            pending = await self._redis.xautoclaim(
                self._stream, self._group, consumer, min_idle_time=60_000, start_id="0-0", count=1
            )
            if len(pending) > 1 and pending[1]:
                message_id, fields = pending[1][0]
                return str(message_id), json.loads(fields["payload"])
        result = await self._redis.xreadgroup(
            self._group, consumer, {self._stream: ">"}, count=1, block=block_ms
        )
        if not result:
            return None
        _, messages = result[0]
        message_id, fields = messages[0]
        return str(message_id), json.loads(fields["payload"])

    async def acknowledge(self, message_id: str) -> None:
        await self._redis.xack(self._stream, self._group, message_id)
