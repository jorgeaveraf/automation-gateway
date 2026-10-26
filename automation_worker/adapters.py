"""Private HTTP integrations and Redis checkpoints for the QBO worker."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import httpx
from redis import Redis

from automation_worker.connection import (
    ConnectionJob,
    PermanentJobError,
    StoredConnection,
)
from automation_worker.n8n_ledger import last_sent_at as read_n8n_last_sent_at


class QboGatewayAdapter:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def update(self, job: ConnectionJob) -> str:
        response = self.client.put(
            f"/clients/{job.client_id}/connection-status",
            json={
                "environment": job.environment,
                "is_connected": job.is_connected,
                "checked_at": job.checked_at.isoformat(),
                "correlation_id": str(job.correlation_id),
            },
        )
        if response.status_code == 404:
            raise PermanentJobError("QBO client or credential no longer exists")
        response.raise_for_status()
        data = response.json()
        outcome = data.get("outcome")
        if outcome not in {"updated", "duplicate", "stale", "conflict"}:
            raise ValueError("Unexpected QBO status update outcome")
        return outcome

    def current(self, job: ConnectionJob) -> StoredConnection:
        response = self.client.get(f"/clients/{job.client_id}")
        if response.status_code == 404:
            raise PermanentJobError("QBO client no longer exists after status update")
        response.raise_for_status()
        data = response.json()
        credentials = data.get("credentials")
        if not isinstance(credentials, list):
            raise TypeError("QBO detail omitted credentials")
        matches = [item for item in credentials if item.get("environment") == job.environment]
        if len(matches) != 1 or not isinstance(matches[0].get("is_connected"), bool):
            raise ValueError("QBO detail has no unique credential for environment")
        raw = matches[0].get("connection_checked_at")
        checked_at = datetime.fromisoformat(raw) if raw else None
        if checked_at is not None and (checked_at.tzinfo is None or checked_at.utcoffset() is None):
            raise ValueError("QBO checked_at has no timezone")
        return StoredConnection(matches[0]["is_connected"], checked_at, data["name"])


class NotificationRouterAdapter:
    """Read confirmed deliveries and dispatch through authenticated n8n webhooks."""

    def __init__(
        self,
        ledger_client: httpx.Client,
        router_client: httpx.Client,
        *,
        ledger_url: str,
        router_url: str,
    ) -> None:
        self.ledger_client = ledger_client
        self.router_client = router_client
        self.ledger_url = ledger_url
        self.router_url = router_url

    def last_sent_at(
        self, *, client_id: UUID, environment: str, recipient: str, scope: str | None
    ) -> datetime | None:
        return read_n8n_last_sent_at(
            self.ledger_client,
            lookup_url=self.ledger_url,
            client_id=client_id,
            environment=environment,
            scope=scope,
        )

    def send(self, request: dict) -> None:
        response = self.router_client.post(self.router_url, json=request)
        response.raise_for_status()


class RedisCheckpoints:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @staticmethod
    def _event_key(event_id: UUID) -> str:
        return f"automation:worker:event:{event_id}"

    @staticmethod
    def _episode_key(client_id: UUID, environment: str) -> str:
        return f"automation:worker:qbo:episode:{client_id}:{environment}"

    def get(self, event_id: UUID, field: str) -> str | None:
        return self.redis.hget(self._event_key(event_id), field)

    def set(self, event_id: UUID, field: str, value: str) -> None:
        key = self._event_key(event_id)
        self.redis.hset(key, field, value)
        self.redis.expire(key, 90 * 24 * 3600)

    def get_episode(self, client_id: UUID, environment: str) -> str | None:
        return self.redis.get(self._episode_key(client_id, environment))

    def set_episode(self, client_id: UUID, environment: str, episode: str) -> None:
        self.redis.set(self._episode_key(client_id, environment), episode)

    def clear_episode(self, client_id: UUID, environment: str) -> None:
        self.redis.delete(self._episode_key(client_id, environment))
