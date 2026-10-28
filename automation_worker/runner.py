"""Single-consumer Redis Lists worker; unfinished jobs remain recoverable."""

from __future__ import annotations

import json
import logging
import os
import time
from uuid import UUID

import httpx
from redis import Redis

from automation_worker.adapters import (
    NotificationRouterAdapter,
    QboGatewayAdapter,
    RedisCheckpoints,
)
from automation_worker.connection import (
    ConnectionJob,
    ConnectionProcessor,
    PermanentJobError,
)

LOGGER = logging.getLogger(__name__)


CLAIM_DUE_SCRIPT = """
local targets = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, 1)
if #targets == 0 then return nil end
local target = targets[1]
local raw = redis.call('RPOPLPUSH', ARGV[2] .. target, KEYS[2])
redis.call('ZREM', KEYS[1], target)
if not raw then redis.call('HDEL', KEYS[3], target) end
return raw
"""

DEFER_IF_BLOCKED_SCRIPT = """
if redis.call('LINDEX', KEYS[1], -1) ~= ARGV[1] then
    return redis.error_reply('Processing job changed before deferral')
end
local owner = redis.call('HGET', KEYS[2], ARGV[2])
if not owner or owner == ARGV[1] then return 'ready' end
redis.call('LREM', KEYS[1], 1, ARGV[1])
redis.call('LPUSH', KEYS[3], ARGV[1])
return 'deferred'
"""

RETRY_SCRIPT = """
if redis.call('LINDEX', KEYS[1], -1) ~= ARGV[1] then
    return redis.error_reply('Processing job changed before retry')
end
local owner = redis.call('HGET', KEYS[2], ARGV[2])
redis.call('LREM', KEYS[1], 1, ARGV[1])
if owner and owner ~= ARGV[1] then
    redis.call('LPUSH', KEYS[4], ARGV[1])
    return 'deferred'
end
if not owner then redis.call('HSET', KEYS[2], ARGV[2], ARGV[1]) end
redis.call('RPUSH', KEYS[4], ARGV[1])
redis.call('ZADD', KEYS[3], ARGV[3], ARGV[2])
return 'retry'
"""

COMPLETE_SCRIPT = """
if redis.call('LINDEX', KEYS[1], -1) ~= ARGV[1] then
    return redis.error_reply('Processing job changed before completion')
end
redis.call('LREM', KEYS[1], 1, ARGV[1])
if redis.call('HGET', KEYS[2], ARGV[2]) == ARGV[1] then
    local next_raw = redis.call('LINDEX', KEYS[4], -1)
    if next_raw then
        redis.call('HSET', KEYS[2], ARGV[2], next_raw)
        redis.call('ZADD', KEYS[3], ARGV[3], ARGV[2])
    else
        redis.call('HDEL', KEYS[2], ARGV[2])
        redis.call('ZREM', KEYS[3], ARGV[2])
    end
end
return 1
"""

DEAD_SCRIPT = """
if redis.call('LINDEX', KEYS[1], -1) ~= ARGV[1] then
    return redis.error_reply('Processing job changed before dead-lettering')
end
redis.call('LREM', KEYS[1], 1, ARGV[1])
redis.call('LPUSH', KEYS[2], ARGV[1])
if redis.call('HGET', KEYS[3], ARGV[2]) == ARGV[1] then
    local next_raw = redis.call('LINDEX', KEYS[5], -1)
    if next_raw then
        redis.call('HSET', KEYS[3], ARGV[2], next_raw)
        redis.call('ZADD', KEYS[4], ARGV[3], ARGV[2])
    else
        redis.call('HDEL', KEYS[3], ARGV[2])
        redis.call('ZREM', KEYS[4], ARGV[2])
    end
end
return 1
"""


class RedisListRunner:
    def __init__(
        self, redis: Redis, processor: ConnectionProcessor, *, queue: str, retry_delay_seconds: int = 5
    ) -> None:
        self.redis = redis
        self.processor = processor
        self.queue = queue
        self.processing = f"{queue}:processing"
        self.dead = f"{queue}:dead"
        self.retry_due = f"{queue}:retry_due"
        self.retry_owner = f"{queue}:retry_owner"
        self.retry_prefix = f"{queue}:retry:"
        self.retry_delay_seconds = retry_delay_seconds

    def _retry_list(self, target: str) -> str:
        return f"{self.retry_prefix}{target}"

    def run_one(self) -> str | None:
        # Resume an unfinished claim first. Due retries and pending jobs are both FIFO.
        raw = self.redis.lindex(self.processing, -1)
        if raw is None:
            raw = self.redis.eval(
                CLAIM_DUE_SCRIPT,
                3,
                self.retry_due,
                self.processing,
                self.retry_owner,
                time.time(),
                self.retry_prefix,
            )
        if raw is None:
            raw = self.redis.blmove(self.queue, self.processing, 1, "RIGHT", "LEFT")
        if raw is None:
            return None

        event_id = None
        try:
            envelope = json.loads(raw)
            event_id = UUID(envelope["event_id"])
            if envelope["kind"] != "qbo.connection_checked.v1":
                raise ValueError("Unexpected job kind on QBO queue")
            job = ConnectionJob.model_validate(envelope["payload"])
        except (ValueError, KeyError, TypeError) as exc:
            LOGGER.error("Invalid job moved to dead-letter queue: %s", exc)
            # The source is the rightmost item because the worker is single-consumer.
            self.redis.lmove(self.processing, self.dead, "RIGHT", "LEFT")
            return "dead"
        target = f"{job.client_id}:{job.environment}"
        disposition = self.redis.eval(
            DEFER_IF_BLOCKED_SCRIPT,
            3,
            self.processing,
            self.retry_owner,
            self._retry_list(target),
            raw,
            target,
        )
        if disposition == "deferred":
            return "deferred"
        try:
            result = self.processor.process(event_id, job)
        except PermanentJobError as exc:
            LOGGER.error("Permanent job failure moved to dead-letter queue: %s", exc)
            self.redis.eval(
                DEAD_SCRIPT,
                5,
                self.processing,
                self.dead,
                self.retry_owner,
                self.retry_due,
                self._retry_list(target),
                raw,
                target,
                time.time(),
            )
            return "dead"
        except Exception:
            LOGGER.exception("Job deferred for target-specific retry: %s", target)
            self.redis.eval(
                RETRY_SCRIPT,
                4,
                self.processing,
                self.retry_owner,
                self.retry_due,
                self._retry_list(target),
                raw,
                target,
                time.time() + self.retry_delay_seconds,
            )
            return "retry"

        self.redis.eval(
            COMPLETE_SCRIPT,
            4,
            self.processing,
            self.retry_owner,
            self.retry_due,
            self._retry_list(target),
            raw,
            target,
            time.time(),
        )
        LOGGER.info("Completed event %s: %s", event_id, result)
        return result


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    required = [
        "REDIS_URL",
        "QBO_GATEWAY_BASE_URL",
        "QBO_GATEWAY_API_KEY",
        "NOTIFICATION_LEDGER_URL",
        "NOTIFICATION_ROUTER_URL",
        "NOTIFICATION_ROUTER_API_KEY",
        "NOTIFICATION_SLACK_DESTINATION_ID",
    ]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Worker is missing configuration: {', '.join(missing)}")
    if os.getenv("NOTIFICATION_ROUTER_RULE_READY") != "true":
        raise RuntimeError("Notification Router rule has not been explicitly verified")

    redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    queue = os.getenv("QBO_CONNECTION_QUEUE", "automation:jobs:qbo.connection_checked.v1")
    with (
        httpx.Client(
            base_url=os.environ["QBO_GATEWAY_BASE_URL"],
            headers={"X-API-Key": os.environ["QBO_GATEWAY_API_KEY"]},
            timeout=15,
        ) as qbo_http,
        httpx.Client(
            headers={"X-API-Key": os.environ["NOTIFICATION_ROUTER_API_KEY"]},
            timeout=15,
        ) as ledger_http,
        httpx.Client(
            headers={"X-API-Key": os.environ["NOTIFICATION_ROUTER_API_KEY"]},
            timeout=60,
        ) as router_http,
    ):
        processor = ConnectionProcessor(
            qbo=QboGatewayAdapter(qbo_http),
            notifications=NotificationRouterAdapter(
                ledger_http,
                router_http,
                ledger_url=os.environ["NOTIFICATION_LEDGER_URL"],
                router_url=os.environ["NOTIFICATION_ROUTER_URL"],
            ),
            checkpoints=RedisCheckpoints(redis),
            recipient=os.environ["NOTIFICATION_SLACK_DESTINATION_ID"],
            additional_user_id=os.getenv("NOTIFICATION_SLACK_ADDITIONAL_USER_ID", "U03PQMKUR6J"),
        )
        runner = RedisListRunner(redis, processor, queue=queue)
        while True:
            runner.run_one()


if __name__ == "__main__":
    main()
