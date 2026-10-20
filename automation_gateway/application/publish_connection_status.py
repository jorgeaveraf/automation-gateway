from uuid import UUID

from automation_gateway.application.ports import ConnectionStatusPublisher
from automation_gateway.schemas.connection_status import (
    ConnectionStatusRequest,
    ConnectionStatusResponse,
)


class PublishConnectionStatus:
    def __init__(self, publisher: ConnectionStatusPublisher) -> None:
        self._publisher = publisher

    async def execute(
        self,
        client_id: UUID,
        request: ConnectionStatusRequest,
    ) -> ConnectionStatusResponse:
        status = ConnectionStatusResponse.from_request(client_id, request)
        await self._publisher.publish(status)
        return status
