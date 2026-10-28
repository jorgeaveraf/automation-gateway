"""QBO connection job handling. The gateway itself remains provider-agnostic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol
from uuid import UUID
import re

from pydantic import BaseModel, ConfigDict, field_validator


class NotificationHint(BaseModel):
    candidate: bool | None = None
    observed_previous_connected: bool | None = None


class PermanentJobError(ValueError):
    """A job cannot succeed by retrying unchanged input."""


class ConnectionJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: UUID
    provider: str
    environment: str
    is_connected: bool
    checked_at: datetime
    correlation_id: UUID
    notification: NotificationHint

    @field_validator("provider")
    @classmethod
    def qbo_only(cls, value: str) -> str:
        if value != "qbo":
            raise ValueError("Only QBO connection jobs are supported")
        return value

    @field_validator("environment")
    @classmethod
    def supported_environment(cls, value: str) -> str:
        if value not in {"prod", "sandbox"}:
            raise ValueError("Unsupported QBO environment")
        return value

    @field_validator("checked_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("checked_at requires a timezone")
        return value.astimezone(UTC)


@dataclass(frozen=True)
class StoredConnection:
    is_connected: bool
    checked_at: datetime | None
    client_name: str
    client_status: str = "active"
    client_updated_at: datetime | None = None


class QboPort(Protocol):
    def update(self, job: ConnectionJob) -> str: ...
    def current(self, job: ConnectionJob) -> StoredConnection: ...


class NotificationPort(Protocol):
    def last_sent_at(
        self, *, client_id: UUID, environment: str, recipient: str, scope: str | None
    ) -> datetime | None: ...

    def send(self, request: dict) -> None: ...


class CheckpointPort(Protocol):
    def get(self, event_id: UUID, field: str) -> str | None: ...
    def set(self, event_id: UUID, field: str, value: str) -> None: ...
    def get_episode(self, client_id: UUID, environment: str) -> str | None: ...
    def set_episode(self, client_id: UUID, environment: str, episode: str) -> None: ...
    def clear_episode(self, client_id: UUID, environment: str) -> None: ...


class ConnectionProcessor:
    def __init__(
        self,
        *,
        qbo: QboPort,
        notifications: NotificationPort,
        checkpoints: CheckpointPort,
        recipient: str,
        reminder_hours: int = 48,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.qbo = qbo
        self.notifications = notifications
        self.checkpoints = checkpoints
        if not re.fullmatch(r"D[A-Z0-9]+", recipient):
            raise ValueError("Slack notification recipient must be a DM conversation ID")
        self.recipient = recipient
        self.reminder_window = timedelta(hours=reminder_hours)
        self.now = now or (lambda: datetime.now(UTC))

    def _skip_ineligible_client(
        self, event_id: UUID, job: ConnectionJob, current: StoredConnection
    ) -> str | None:
        if current.client_status == "inactive":
            self.checkpoints.set(event_id, "done", "inactive")
            return "inactive"
        if current.client_updated_at and current.client_updated_at > job.checked_at:
            self.checkpoints.set(event_id, "done", "superseded")
            return "superseded"
        return None

    def process(self, event_id: UUID, job: ConnectionJob) -> str:
        if self.checkpoints.get(event_id, "done"):
            return "duplicate"

        skipped = self._skip_ineligible_client(event_id, job, self.qbo.current(job))
        if skipped:
            return skipped

        if not self.checkpoints.get(event_id, "persisted"):
            outcome = self.qbo.update(job)
            if outcome == "conflict":
                raise PermanentJobError("QBO rejected conflicting status for the same timestamp")
            self.checkpoints.set(event_id, "persisted", outcome)

        current = self.qbo.current(job)
        skipped = self._skip_ineligible_client(event_id, job, current)
        if skipped:
            return skipped
        if current.checked_at is None:
            raise ValueError("QBO status has no checked_at after persistence")
        current_time = current.checked_at.astimezone(UTC)
        if current_time < job.checked_at:
            raise ValueError("QBO did not persist this or a newer connection check")
        if current_time > job.checked_at:
            self.checkpoints.set(event_id, "done", "superseded")
            return "superseded"
        if current.is_connected != job.is_connected:
            raise ValueError("QBO returned a different state for this check")

        if job.is_connected:
            self.checkpoints.clear_episode(job.client_id, job.environment)
            self.checkpoints.set(event_id, "done", "connected")
            return "connected"

        episode = self.checkpoints.get(event_id, "episode")
        if not episode:
            episode = self.checkpoints.get_episode(job.client_id, job.environment)
            if job.notification.observed_previous_connected or not episode:
                episode = str(event_id)
                self.checkpoints.set_episode(job.client_id, job.environment, episode)
            self.checkpoints.set(event_id, "episode", episode)

        scope = f"qbo_connection_disconnected:{job.client_id}:{job.environment}:{episode}"
        last = self.notifications.last_sent_at(
            client_id=job.client_id,
            environment=job.environment,
            recipient=self.recipient,
            scope=scope,
        )
        if last is None and not job.notification.observed_previous_connected and episode == str(event_id):
            last = self.notifications.last_sent_at(
                client_id=job.client_id,
                environment=job.environment,
                recipient=self.recipient,
                scope=None,
            )
        if last is not None and self.now() - last.astimezone(UTC) < self.reminder_window:
            self.checkpoints.set(event_id, "done", "suppressed")
            return "suppressed"

        # The router's delivery table owns final sent/dedup state. On a retry the
        # same request_id is reused, including after an ambiguous HTTP failure.
        request_id = f"{scope}:slack:{self.recipient}:" + (
            "initial" if last is None else f"after:{last.astimezone(UTC).isoformat()}"
        )
        request = {
            "contract_type": "notification_router.request",
            "contract_version": "1.0",
            "event_type": "qbo_connection_disconnected",
            "source": {
                "workflow_name": "QBO Connection Monitor",
                "node_name": "Automation Worker",
            },
            "entity": {
                "entity_name": current.client_name,
                "client_id": str(job.client_id),
                "environment": job.environment,
            },
            "execution": {
                "source_execution_id": str(event_id),
                "request_id": request_id,
                "original_input_index": 0,
                "occurred_at": job.checked_at.isoformat(),
            },
            "error": {
                "present": True,
                "message": f"QuickBooks connection is disconnected for {current.client_name} ({job.environment}).",
                "name": "QboConnectionDisconnected",
                "code": "QBO_CONNECTION_DISCONNECTED",
                "error_type": "authorization",
                "provider": "intuit",
                "action_required": "reconnect_quickbooks",
                "retryable": False,
            },
            "context": {
                "notification_scope_key": scope,
                "channel": "slack",
                "recipient": self.recipient,
                "notification_recipient": self.recipient,
                "notification_destination_type": "channel",
                "checked_at": job.checked_at.isoformat(),
                "communication": {
                    "destination_type": "channel",
                    "recipient": self.recipient,
                    "metadata": {
                        "notification_scope_key": scope,
                        "client_id": str(job.client_id),
                        "environment": job.environment,
                    },
                },
            },
            "compatibility": {"response_profile": "default", "original_input_index": 0},
        }
        skipped = self._skip_ineligible_client(event_id, job, self.qbo.current(job))
        if skipped:
            return skipped
        self.notifications.send(request)
        confirmed = self.notifications.last_sent_at(
            client_id=job.client_id,
            environment=job.environment,
            recipient=self.recipient,
            scope=scope,
        )
        if confirmed is None or confirmed < job.checked_at:
            raise RuntimeError("Notification Router did not confirm a sent delivery")
        self.checkpoints.set(event_id, "done", "notified")
        return "notified"
