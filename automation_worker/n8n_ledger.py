"""Read confirmed deliveries through the authenticated Notification Router webhook."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import httpx


def last_sent_at(
    client: httpx.Client,
    *,
    lookup_url: str,
    client_id: UUID,
    environment: str,
    recipient: str,
    scope: str | None = None,
) -> datetime | None:
    request = {"client_id": str(client_id), "environment": environment, "recipient": recipient}
    if scope is not None:
        request["notification_scope_key"] = scope
    response = client.post(lookup_url, json=request)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("result_type") != "notification_ledger.last_sent.v1":
        raise ValueError("Unexpected notification ledger response")
    if "last_notified_at" not in payload:
        raise ValueError("Notification ledger response omitted last_notified_at")
    raw = payload["last_notified_at"]
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError("Notification ledger timestamp is not a string")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Notification ledger timestamp has no timezone")
    return parsed.astimezone(UTC)
