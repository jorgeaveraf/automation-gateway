from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from automation_gateway.application.ports import JobQueue
from automation_gateway.core.config import Settings, get_settings
from automation_gateway.core.errors import JobQueueNotConfiguredError
from automation_gateway.infrastructure.redis_job_queue import RedisListJobQueue


class UnconfiguredJobQueue:
    async def enqueue(self, job) -> bool:
        raise JobQueueNotConfiguredError("Redis job queue is not configured")


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    configured = settings.automation_gateway_api_key
    if configured is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service authentication is not configured",
        )
    if x_api_key is None or not compare_digest(
        x_api_key,
        configured.get_secret_value(),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


def get_job_queue(
    settings: Settings = Depends(get_settings),
) -> JobQueue:
    if not settings.redis_url or not settings.redis_job_queues:
        return UnconfiguredJobQueue()
    return RedisListJobQueue(
        redis_url=settings.redis_url,
        queue_by_kind=settings.redis_job_queues,
        deduplication_ttl_seconds=settings.job_deduplication_ttl_seconds,
    )
