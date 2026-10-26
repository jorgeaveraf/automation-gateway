"""Test-only ASGI app that accepts publications without external side effects."""

from automation_gateway.api.dependencies import get_job_queue
from automation_gateway.app import app


class LocalFakeQueue:
    async def enqueue(self, _job) -> bool:
        return True


app.dependency_overrides[get_job_queue] = LocalFakeQueue
