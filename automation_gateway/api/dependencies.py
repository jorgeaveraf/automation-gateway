from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from automation_gateway.application.ports import ConnectionStatusPublisher
from automation_gateway.core.config import Settings, get_settings
from automation_gateway.core.errors import PublisherNotConfiguredError
from automation_gateway.infrastructure.qbo_gateway_publisher import (
    QboGatewayConnectionStatusPublisher,
)


class UnconfiguredConnectionStatusPublisher:
    async def publish(self, status_update) -> None:
        raise PublisherNotConfiguredError(
            "Connection status publisher is not configured"
        )


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


def get_connection_status_publisher(
    settings: Settings = Depends(get_settings),
) -> ConnectionStatusPublisher:
    base_url = settings.qbo_gateway_base_url
    api_key = settings.qbo_gateway_api_key
    if not base_url or api_key is None:
        return UnconfiguredConnectionStatusPublisher()
    return QboGatewayConnectionStatusPublisher(
        base_url=base_url,
        api_key=api_key.get_secret_value(),
        timeout_seconds=settings.qbo_gateway_timeout_seconds,
    )
