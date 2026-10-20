import httpx

from automation_gateway.core.errors import (
    PublisherTimeoutError,
    PublisherUnavailableError,
)
from automation_gateway.schemas.connection_status import ConnectionStatusResponse


class QboGatewayConnectionStatusPublisher:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def publish(self, status_update: ConnectionStatusResponse) -> None:
        payload = {
            "environment": status_update.environment.value,
            "is_connected": status_update.is_connected,
            "checked_at": status_update.checked_at.isoformat(),
            "correlation_id": str(status_update.correlation_id),
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "X-API-Key": self._api_key,
                    "Accept": "application/json",
                },
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.put(
                    f"/clients/{status_update.client_id}/connection-status",
                    json=payload,
                    headers={"X-Request-Id": str(status_update.correlation_id)},
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise PublisherTimeoutError("QBO Gateway publication timed out") from exc
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            raise PublisherUnavailableError("QBO Gateway publication failed") from exc
