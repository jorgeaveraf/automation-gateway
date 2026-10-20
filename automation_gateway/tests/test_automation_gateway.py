from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from automation_gateway.core.config import get_settings
from automation_gateway.core.errors import (
    PublisherTimeoutError,
    PublisherUnavailableError,
)


CLIENT_ID = "070b2e37-aa28-4911-b2b2-e493678d38f5"
CORRELATION_ID = "7ac383c5-7d11-488f-8ba8-11bd2c02023d"
API_KEY = "local-test-api-key"


class FakeConnectionStatusPublisher:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, status) -> None:
        self.published.append(status)


@pytest.fixture(autouse=True)
def configure_local_auth(monkeypatch):
    monkeypatch.setenv("AUTOMATION_GATEWAY_API_KEY", API_KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client_with_publisher() -> Iterator[tuple[TestClient, FakeConnectionStatusPublisher]]:
    from automation_gateway.api.dependencies import get_connection_status_publisher
    from automation_gateway.app import app

    publisher = FakeConnectionStatusPublisher()
    app.dependency_overrides[get_connection_status_publisher] = lambda: publisher
    with TestClient(app) as client:
        yield client, publisher
    app.dependency_overrides.clear()


def valid_payload() -> dict:
    return {
        "provider": "qbo",
        "environment": "prod",
        "is_connected": True,
        "checked_at": "2026-09-25T15:30:00Z",
        "correlation_id": CORRELATION_ID,
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


def test_publishes_valid_connection_status(client_with_publisher) -> None:
    client, publisher = client_with_publisher
    response = client.put(
        f"/v1/connections/{CLIENT_ID}/status",
        headers={"X-API-Key": API_KEY},
        json=valid_payload(),
    )

    assert response.status_code == 200
    assert response.json()["client_id"] == CLIENT_ID
    assert response.json()["is_connected"] is True
    assert len(publisher.published) == 1
    assert str(publisher.published[0].correlation_id) == CORRELATION_ID


def test_rejects_missing_api_key(client_with_publisher) -> None:
    client, publisher = client_with_publisher
    response = client.put(
        f"/v1/connections/{CLIENT_ID}/status",
        json=valid_payload(),
    )

    assert response.status_code == 401
    assert publisher.published == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("environment", "production"),
        ("is_connected", "true"),
        ("checked_at", "2026-09-25T15:30:00"),
        ("correlation_id", "not-a-uuid"),
    ],
)
def test_rejects_invalid_payload(client_with_publisher, field, value) -> None:
    client, publisher = client_with_publisher
    payload = valid_payload()
    payload[field] = value
    response = client.put(
        f"/v1/connections/{CLIENT_ID}/status",
        headers={"X-API-Key": API_KEY},
        json=payload,
    )

    assert response.status_code == 422
    assert publisher.published == []


def test_rejects_invalid_client_id(client_with_publisher) -> None:
    client, publisher = client_with_publisher
    response = client.put(
        "/v1/connections/not-a-uuid/status",
        headers={"X-API-Key": API_KEY},
        json=valid_payload(),
    )

    assert response.status_code == 422
    assert publisher.published == []


def test_publishes_disconnected_status(client_with_publisher) -> None:
    client, publisher = client_with_publisher
    payload = valid_payload()
    payload["is_connected"] = False

    response = client.put(
        f"/v1/connections/{CLIENT_ID}/status",
        headers={"X-API-Key": API_KEY},
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["is_connected"] is False
    assert publisher.published[0].is_connected is False


def test_returns_503_until_real_publisher_is_configured() -> None:
    from automation_gateway.app import app

    with TestClient(app) as client:
        response = client.put(
            f"/v1/connections/{CLIENT_ID}/status",
            headers={"X-API-Key": API_KEY},
            json=valid_payload(),
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Connection status publisher is not configured"


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (PublisherUnavailableError("QBO Gateway publication failed"), 502),
        (PublisherTimeoutError("QBO Gateway publication timed out"), 504),
    ],
)
def test_translates_publisher_errors(error, expected_status) -> None:
    from automation_gateway.api.dependencies import get_connection_status_publisher
    from automation_gateway.app import app

    class FailingPublisher:
        async def publish(self, _status) -> None:
            raise error

    app.dependency_overrides[get_connection_status_publisher] = FailingPublisher
    try:
        response = TestClient(app).put(
            f"/v1/connections/{CLIENT_ID}/status",
            headers={"X-API-Key": API_KEY},
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == expected_status
