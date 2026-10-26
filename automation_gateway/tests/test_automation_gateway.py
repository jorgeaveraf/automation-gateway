from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from automation_gateway.core.config import get_settings
from automation_gateway.core.errors import JobQueueUnavailableError


EVENT_ID = "070b2e37-aa28-4911-b2b2-e493678d38f5"
API_KEY = "local-test-api-key"
JOB_KIND = "qbo.connection_checked.v1"


class FakeJobQueue:
    def __init__(self) -> None:
        self.jobs = []
        self.event_ids = set()

    async def enqueue(self, job) -> bool:
        if str(job.event_id) in self.event_ids:
            return False
        self.event_ids.add(str(job.event_id))
        self.jobs.append(job)
        return True


@pytest.fixture(autouse=True)
def configure_local_auth(monkeypatch):
    monkeypatch.setenv("AUTOMATION_GATEWAY_API_KEY", API_KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client_with_queue() -> Iterator[tuple[TestClient, FakeJobQueue]]:
    from automation_gateway.api.dependencies import get_job_queue
    from automation_gateway.app import app

    queue = FakeJobQueue()
    app.dependency_overrides[get_job_queue] = lambda: queue
    with TestClient(app) as client:
        yield client, queue
    app.dependency_overrides.clear()


def valid_job() -> dict:
    return {
        "event_id": EVENT_ID,
        "kind": JOB_KIND,
        "payload": {
            "client_id": "client opaque to gateway",
            "environment": "prod",
            "is_connected": True,
            "checked_at": "2026-09-25T15:30:00Z",
            "correlation_id": "7ac383c5-7d11-488f-8ba8-11bd2c02023d",
            "notification_candidate": {"should_notify": True},
        },
    }


def test_health_is_public_and_local() -> None:
    from automation_gateway.app import app

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "automation-gateway",
        "version": "0.1.0",
    }


def test_accepts_generic_job_without_interpreting_payload(client_with_queue) -> None:
    client, queue = client_with_queue
    payload = valid_job()
    response = client.post(
        "/v1/jobs",
        headers={"X-API-Key": API_KEY},
        json=payload,
    )

    assert response.status_code == 202
    assert response.json() == {"event_id": EVENT_ID, "accepted": True, "duplicate": False}
    assert len(queue.jobs) == 1
    assert queue.jobs[0].payload == payload["payload"]


def test_returns_duplicate_acceptance_for_repeated_event_id(client_with_queue) -> None:
    client, queue = client_with_queue
    for _ in range(2):
        response = client.post(
            "/v1/jobs",
            headers={"X-API-Key": API_KEY},
            json=valid_job(),
        )

    assert response.status_code == 202
    assert response.json() == {"event_id": EVENT_ID, "accepted": True, "duplicate": True}
    assert len(queue.jobs) == 1


def test_rejects_missing_api_key(client_with_queue) -> None:
    client, queue = client_with_queue
    response = client.post("/v1/jobs", json=valid_job())

    assert response.status_code == 401
    assert queue.jobs == []


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": JOB_KIND, "payload": {}},
        {"event_id": "not-a-uuid", "kind": JOB_KIND, "payload": {}},
        {"event_id": EVENT_ID, "kind": "", "payload": {}},
        {"event_id": EVENT_ID, "kind": JOB_KIND, "payload": []},
        {"event_id": EVENT_ID, "kind": JOB_KIND, "payload": {}, "extra": True},
    ],
)
def test_rejects_invalid_job_envelope(client_with_queue, payload) -> None:
    client, queue = client_with_queue
    response = client.post(
        "/v1/jobs",
        headers={"X-API-Key": API_KEY},
        json=payload,
    )

    assert response.status_code == 422
    assert queue.jobs == []


def test_returns_503_until_redis_is_configured(monkeypatch) -> None:
    from automation_gateway.app import app

    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_JOB_QUEUES", raising=False)
    get_settings.cache_clear()
    try:
        response = TestClient(app).post(
            "/v1/jobs",
            headers={"X-API-Key": API_KEY},
            json=valid_job(),
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Redis job queue is not configured"


def test_does_not_accept_job_when_redis_write_is_unconfirmed() -> None:
    from automation_gateway.api.dependencies import get_job_queue
    from automation_gateway.app import app

    class FailingQueue:
        async def enqueue(self, _job) -> bool:
            raise JobQueueUnavailableError("Redis job queue is unavailable")

    app.dependency_overrides[get_job_queue] = FailingQueue
    try:
        response = TestClient(app).post(
            "/v1/jobs",
            headers={"X-API-Key": API_KEY},
            json=valid_job(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Redis job queue is unavailable"
