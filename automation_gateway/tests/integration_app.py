"""Test-only ASGI app that accepts publications without external side effects."""

from automation_gateway.api.dependencies import get_connection_status_publisher
from automation_gateway.app import app


class LocalFakePublisher:
    async def publish(self, _status_update) -> None:
        return None


app.dependency_overrides[get_connection_status_publisher] = LocalFakePublisher
