import json
from uuid import UUID

import pytest
from redis.exceptions import ConnectionError

from automation_gateway.core.errors import JobQueueUnavailableError, UnsupportedJobKindError
from automation_gateway.infrastructure.redis_job_queue import (
    ENQUEUE_ONCE_SCRIPT,
    RedisListJobQueue,
)
from automation_gateway.schemas.jobs import JobEnvelope


EVENT_ID = UUID("070b2e37-aa28-4911-b2b2-e493678d38f5")


class FakeRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.seen = set()
        self.lists = {}
        self.closed = False
        self.ttls = {}

    async def eval(self, script, numkeys, dedup_key, queue_key, payload, ttl):
        assert script == ENQUEUE_ONCE_SCRIPT
        assert numkeys == 2
        if self.fail:
            raise ConnectionError("unavailable")
        if dedup_key in self.seen:
            return 0
        self.lists.setdefault(queue_key, []).insert(0, payload)
        self.seen.add(dedup_key)
        self.ttls[dedup_key] = int(ttl)
        return 1

    async def aclose(self):
        self.closed = True


def job(kind: str = "qbo.connection_checked.v1") -> JobEnvelope:
    return JobEnvelope(
        event_id=EVENT_ID,
        kind=kind,
        payload={"client_id": "opaque", "nested": [1, True]},
    )


@pytest.mark.asyncio
async def test_redis_queue_atomically_routes_and_deduplicates(monkeypatch) -> None:
    import automation_gateway.infrastructure.redis_job_queue as module

    fake = FakeRedis()
    monkeypatch.setattr(module.Redis, "from_url", lambda *_args, **_kwargs: fake)
    queue = RedisListJobQueue(
        redis_url="redis://unused",
        queue_by_kind={"qbo.connection_checked.v1": "jobs:qbo"},
        deduplication_ttl_seconds=3600,
    )

    assert await queue.enqueue(job()) is True
    assert await queue.enqueue(job()) is False
    assert len(fake.lists["jobs:qbo"]) == 1
    assert json.loads(fake.lists["jobs:qbo"][0]) == job().model_dump(mode="json")
    assert fake.ttls[f"automation:jobs:dedup:{EVENT_ID}"] == 3600
    assert fake.closed is True


@pytest.mark.asyncio
async def test_redis_queue_keeps_oldest_job_on_right_for_fifo_worker(monkeypatch) -> None:
    import automation_gateway.infrastructure.redis_job_queue as module

    fake = FakeRedis()
    monkeypatch.setattr(module.Redis, "from_url", lambda *_args, **_kwargs: fake)
    queue = RedisListJobQueue(
        redis_url="redis://unused",
        queue_by_kind={"qbo.connection_checked.v1": "jobs:qbo"},
        deduplication_ttl_seconds=3600,
    )
    older = job()
    newer = JobEnvelope(
        event_id=UUID("070b2e37-aa28-4911-b2b2-e493678d38f6"),
        kind=older.kind,
        payload=older.payload,
    )

    assert await queue.enqueue(older) is True
    assert await queue.enqueue(newer) is True
    assert [json.loads(raw)["event_id"] for raw in reversed(fake.lists["jobs:qbo"])] == [
        str(older.event_id),
        str(newer.event_id),
    ]


@pytest.mark.asyncio
async def test_redis_queue_does_not_inspect_payload_for_routing(monkeypatch) -> None:
    import automation_gateway.infrastructure.redis_job_queue as module

    fake = FakeRedis()
    monkeypatch.setattr(module.Redis, "from_url", lambda *_args, **_kwargs: fake)
    queue = RedisListJobQueue(
        redis_url="redis://unused",
        queue_by_kind={"other.kind.v1": "jobs:other"},
        deduplication_ttl_seconds=3600,
    )

    with pytest.raises(UnsupportedJobKindError):
        await queue.enqueue(job())
    assert fake.lists == {}


@pytest.mark.asyncio
async def test_redis_error_is_reported_as_unconfirmed_enqueue(monkeypatch) -> None:
    import automation_gateway.infrastructure.redis_job_queue as module

    fake = FakeRedis(fail=True)
    monkeypatch.setattr(module.Redis, "from_url", lambda *_args, **_kwargs: fake)
    queue = RedisListJobQueue(
        redis_url="redis://unused",
        queue_by_kind={"qbo.connection_checked.v1": "jobs:qbo"},
        deduplication_ttl_seconds=3600,
    )

    with pytest.raises(JobQueueUnavailableError):
        await queue.enqueue(job())
    assert fake.lists == {}
    assert fake.closed is True
