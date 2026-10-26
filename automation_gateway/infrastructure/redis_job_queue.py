import json

from redis.asyncio import Redis
from redis.exceptions import RedisError

from automation_gateway.core.errors import (
    JobQueueUnavailableError,
    UnsupportedJobKindError,
)
from automation_gateway.schemas.jobs import JobEnvelope


ENQUEUE_ONCE_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    return 0
end
-- The worker claims from the right, so prepend new jobs to preserve FIFO order.
redis.call('LPUSH', KEYS[2], ARGV[1])
redis.call('SET', KEYS[1], '1', 'EX', ARGV[2])
return 1
"""


class RedisListJobQueue:
    def __init__(
        self,
        *,
        redis_url: str,
        queue_by_kind: dict[str, str],
        deduplication_ttl_seconds: int,
    ) -> None:
        self._redis_url = redis_url
        self._queue_by_kind = queue_by_kind
        self._deduplication_ttl_seconds = deduplication_ttl_seconds

    async def enqueue(self, job: JobEnvelope) -> bool:
        queue_key = self._queue_by_kind.get(job.kind)
        if queue_key is None:
            raise UnsupportedJobKindError(f"Unsupported job kind: {job.kind}")

        event_id = str(job.event_id)
        deduplication_key = f"automation:jobs:dedup:{event_id}"
        serialized_job = json.dumps(
            job.model_dump(mode="json"),
            separators=(",", ":"),
            ensure_ascii=False,
        )

        redis = Redis.from_url(self._redis_url, decode_responses=True)
        try:
            result = await redis.eval(
                ENQUEUE_ONCE_SCRIPT,
                2,
                deduplication_key,
                queue_key,
                serialized_job,
                self._deduplication_ttl_seconds,
            )
            return bool(result)
        except RedisError as exc:
            raise JobQueueUnavailableError("Redis job queue is unavailable") from exc
        finally:
            await redis.aclose()
