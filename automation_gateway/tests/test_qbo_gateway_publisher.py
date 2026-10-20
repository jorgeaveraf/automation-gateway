import json
from datetime import datetime
from uuid import UUID

import httpx
import pytest

from automation_gateway.core.errors import (
    PublisherTimeoutError,
    PublisherUnavailableError,
)
from automation_gateway.infrastructure.qbo_gateway_publisher import (
    QboGatewayConnectionStatusPublisher,
)
from automation_gateway.schemas.connection_status import (
    ConnectionEnvironment,
    ConnectionStatusResponse,
)


CLIENT_ID = UUID("070b2e37-aa28-4911-b2b2-e493678d38f5")
CORRELATION_ID = UUID("7ac383c5-7d11-488f-8ba8-11bd2c02023d")


def status_update(*, is_connected: bool = True) -> ConnectionStatusResponse:
    return ConnectionStatusResponse(
        client_id=CLIENT_ID,
        environment=ConnectionEnvironment.PROD,
        is_connected=is_connected,
        checked_at=datetime.fromisoformat("2026-10-19T12:00:00-06:00"),
        correlation_id=CORRELATION_ID,
    )


@pytest.mark.asyncio
async def test_publishes_qbo_gateway_contract() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "client_id": str(CLIENT_ID),
                "environment": "prod",
                "is_connected": True,
                "connection_checked_at": "2026-10-19T18:00:00Z",
                "applied": True,
                "outcome": "updated",
            },
        )

    publisher = QboGatewayConnectionStatusPublisher(
        base_url="http://qbo.local",
        api_key="local-admin-key",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    await publisher.publish(status_update())

    request = captured["request"]
    assert request.method == "PUT"
    assert request.url.path == f"/clients/{CLIENT_ID}/connection-status"
    assert request.headers["X-API-Key"] == "local-admin-key"
    assert request.headers["X-Request-Id"] == str(CORRELATION_ID)
    assert json.loads(request.content) == {
        "environment": "prod",
        "is_connected": True,
        "checked_at": "2026-10-19T12:00:00-06:00",
        "correlation_id": str(CORRELATION_ID),
    }


@pytest.mark.asyncio
async def test_translates_qbo_gateway_http_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "unauthorized"})

    publisher = QboGatewayConnectionStatusPublisher(
        base_url="http://qbo.local",
        api_key="wrong-key",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(PublisherUnavailableError, match="publication failed"):
        await publisher.publish(status_update())


@pytest.mark.asyncio
async def test_translates_qbo_gateway_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    publisher = QboGatewayConnectionStatusPublisher(
        base_url="http://qbo.local",
        api_key="local-admin-key",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(PublisherTimeoutError, match="timed out"):
        await publisher.publish(status_update(is_connected=False))
