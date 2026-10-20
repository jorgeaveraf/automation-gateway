from typing import Protocol

from automation_gateway.schemas.connection_status import ConnectionStatusResponse


class ConnectionStatusPublisher(Protocol):
    async def publish(self, status: ConnectionStatusResponse) -> None:
        """Publish the latest observed connection status to its owning service."""
