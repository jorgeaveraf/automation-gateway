from typing import Protocol

from automation_gateway.schemas.jobs import JobEnvelope


class JobQueue(Protocol):
    async def enqueue(self, job: JobEnvelope) -> bool:
        """Atomically enqueue a new job, returning False for duplicate event IDs."""
