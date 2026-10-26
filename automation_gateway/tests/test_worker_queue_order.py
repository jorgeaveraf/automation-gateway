"""Ordering and target-isolated retry behavior for the Redis Lists consumer."""

import json
from uuid import UUID

from automation_worker.runner import (
    CLAIM_DUE_SCRIPT,
    COMPLETE_SCRIPT,
    DEAD_SCRIPT,
    DEFER_IF_BLOCKED_SCRIPT,
    RETRY_SCRIPT,
    RedisListRunner,
)
from automation_worker.connection import PermanentJobError


CLIENT_A = "477751f2-1142-4283-a3c0-387f8aa45fbd"
CLIENT_B = "070b2e37-aa28-4911-b2b2-e493678d38f5"


def job(event_id: int, client_id: str) -> str:
    return json.dumps(
        {
            "event_id": str(UUID(int=event_id)),
            "kind": "qbo.connection_checked.v1",
            "payload": {
                "client_id": client_id,
                "provider": "qbo",
                "environment": "sandbox",
                "is_connected": True,
                "checked_at": "2026-10-23T12:00:00+00:00",
                "correlation_id": str(UUID(int=event_id)),
                "notification": {"candidate": None, "observed_previous_connected": None},
            },
        }
    )


class FakeRedis:
    def __init__(self):
        self.lists = {}
        self.owners = {}
        self.due = {}

    def lindex(self, key, index):
        items = self.lists.get(key, [])
        return items[index] if items else None

    def blmove(self, source, destination, timeout, wherefrom, whereto):
        assert (timeout, wherefrom, whereto) == (1, "RIGHT", "LEFT")
        if not self.lists.get(source):
            return None
        raw = self.lists[source].pop()
        self.lists.setdefault(destination, []).insert(0, raw)
        return raw

    def lmove(self, source, destination, wherefrom, whereto):
        assert (wherefrom, whereto) == ("RIGHT", "LEFT")
        raw = self.lists[source].pop()
        self.lists.setdefault(destination, []).insert(0, raw)
        return raw

    def eval(self, script, count, *args):
        if script == CLAIM_DUE_SCRIPT:
            due_key, processing, owners, now, prefix = args
            assert count == 3
            ready = sorted((score, target) for target, score in self.due.items() if score <= now)
            if not ready:
                return None
            target = ready[0][1]
            self.due.pop(target)
            blocked = self.lists.get(prefix + target, [])
            if not blocked:
                self.owners.pop(target, None)
                return None
            raw = blocked.pop()
            self.lists.setdefault(processing, []).insert(0, raw)
            return raw
        if script == DEFER_IF_BLOCKED_SCRIPT:
            processing, owners, blocked, raw, target = args
            assert count == 3 and self.lindex(processing, -1) == raw
            owner = self.owners.get(target)
            if not owner or owner == raw:
                return "ready"
            self.lists[processing].remove(raw)
            self.lists.setdefault(blocked, []).insert(0, raw)
            return "deferred"
        if script == RETRY_SCRIPT:
            processing, owners, due, blocked, raw, target, retry_at = args
            assert count == 4 and self.lindex(processing, -1) == raw
            self.lists[processing].remove(raw)
            owner = self.owners.get(target)
            if owner and owner != raw:
                self.lists.setdefault(blocked, []).insert(0, raw)
                return "deferred"
            self.owners[target] = raw
            self.lists.setdefault(blocked, []).append(raw)
            self.due[target] = retry_at
            return "retry"
        if script == COMPLETE_SCRIPT:
            processing, owners, due, blocked, raw, target, now = args
            assert count == 4 and self.lindex(processing, -1) == raw
            self.lists[processing].remove(raw)
            if self.owners.get(target) == raw:
                next_raw = self.lindex(blocked, -1)
                if next_raw:
                    self.owners[target] = next_raw
                    self.due[target] = now
                else:
                    self.owners.pop(target)
                    self.due.pop(target, None)
            return 1
        if script == DEAD_SCRIPT:
            processing, dead, owners, due, blocked, raw, target, now = args
            assert count == 5 and self.lindex(processing, -1) == raw
            self.lists[processing].remove(raw)
            self.lists.setdefault(dead, []).insert(0, raw)
            if self.owners.get(target) == raw:
                next_raw = self.lindex(blocked, -1)
                if next_raw:
                    self.owners[target] = next_raw
                    self.due[target] = now
                else:
                    self.owners.pop(target)
                    self.due.pop(target, None)
            return 1
        raise AssertionError("Unexpected Lua script")


class FakeProcessor:
    def __init__(self, *, fail_once=None, permanent=None):
        self.fail_once = set(fail_once or [])
        self.permanent = set(permanent or [])
        self.processed = []

    def process(self, event_id, connection_job):
        self.processed.append(event_id)
        if event_id in self.permanent:
            raise PermanentJobError("Simulated removed credential")
        if event_id in self.fail_once:
            self.fail_once.remove(event_id)
            raise RuntimeError("Simulated transient dependency failure")
        return "connected"


def test_pending_jobs_are_consumed_oldest_first(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("automation_worker.runner.time.time", lambda: clock[0])
    redis = FakeRedis()
    processor = FakeProcessor()
    runner = RedisListRunner(redis, processor, queue="jobs")
    redis.lists["jobs"] = [job(2, CLIENT_A), job(1, CLIENT_A)]

    assert runner.run_one() == "connected"
    assert runner.run_one() == "connected"
    assert processor.processed == [UUID(int=1), UUID(int=2)]


def test_failed_target_retries_without_blocking_others_or_overtaking_itself(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("automation_worker.runner.time.time", lambda: clock[0])
    redis = FakeRedis()
    processor = FakeProcessor(fail_once={UUID(int=1)})
    runner = RedisListRunner(redis, processor, queue="jobs", retry_delay_seconds=5)
    # LPUSH order: A1, A2, B1. A2 must wait for A1, while B1 may proceed.
    redis.lists["jobs"] = [job(3, CLIENT_B), job(2, CLIENT_A), job(1, CLIENT_A)]

    assert runner.run_one() == "retry"
    assert runner.run_one() == "deferred"
    assert runner.run_one() == "connected"
    assert processor.processed == [UUID(int=1), UUID(int=3)]

    # Recreate the runner to verify that the Redis-backed blocked lane survives restart.
    runner = RedisListRunner(redis, processor, queue="jobs", retry_delay_seconds=5)
    clock[0] = 106.0
    assert runner.run_one() == "connected"
    assert runner.run_one() == "connected"
    assert processor.processed == [UUID(int=1), UUID(int=3), UUID(int=1), UUID(int=2)]
    assert redis.owners == {}
    assert redis.due == {}


def test_permanent_failure_is_recoverable_in_dead_letter_and_releases_target(monkeypatch):
    monkeypatch.setattr("automation_worker.runner.time.time", lambda: 100.0)
    redis = FakeRedis()
    processor = FakeProcessor(permanent={UUID(int=1)})
    runner = RedisListRunner(redis, processor, queue="jobs")
    redis.lists["jobs"] = [job(2, CLIENT_A), job(1, CLIENT_A)]

    assert runner.run_one() == "dead"
    assert runner.run_one() == "connected"
    assert [json.loads(raw)["event_id"] for raw in redis.lists["jobs:dead"]] == [
        str(UUID(int=1))
    ]
    assert redis.owners == {}
