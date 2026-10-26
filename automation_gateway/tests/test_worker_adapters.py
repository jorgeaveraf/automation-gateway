import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from automation_worker.adapters import NotificationRouterAdapter, QboGatewayAdapter
from automation_worker.connection import ConnectionJob, PermanentJobError

CLIENT_ID = UUID("477751f2-1142-4283-a3c0-387f8aa45fbd")
EVENT_ID = UUID("477751f2-1142-4283-a3c0-387f8aa45fbe")
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def job():
    return ConnectionJob(
        client_id=CLIENT_ID,
        provider="qbo",
        environment="sandbox",
        is_connected=False,
        checked_at=NOW,
        correlation_id=EVENT_ID,
        notification={},
    )


def test_qbo_adapter_uses_existing_status_contract_and_reads_detail():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "PUT":
            return httpx.Response(200, json={"outcome": "updated"})
        return httpx.Response(
            200,
            json={
                "name": "ACME Sandbox",
                "credentials": [
                    {
                        "environment": "sandbox",
                        "is_connected": False,
                        "connection_checked_at": NOW.isoformat(),
                    }
                ],
            },
        )

    with httpx.Client(
        base_url="http://qbo.local",
        headers={"X-API-Key": "local"},
        transport=httpx.MockTransport(handler),
    ) as client:
        adapter = QboGatewayAdapter(client)
        assert adapter.update(job()) == "updated"
        state = adapter.current(job())
    assert state.client_name == "ACME Sandbox"
    assert state.checked_at == NOW
    assert requests[0].url.path == f"/clients/{CLIENT_ID}/connection-status"
    assert requests[1].url.path == f"/clients/{CLIENT_ID}"


@pytest.mark.parametrize("method", ["PUT", "GET"])
def test_missing_qbo_target_is_permanent(method):
    def handler(request):
        if request.method == method:
            return httpx.Response(404, json={"message": "Credential not found"})
        return httpx.Response(200, json={"outcome": "updated"})

    with httpx.Client(base_url="http://qbo.local", transport=httpx.MockTransport(handler)) as client:
        adapter = QboGatewayAdapter(client)
        with pytest.raises(PermanentJobError, match="no longer exists"):
            if method == "PUT":
                adapter.update(job())
            else:
                adapter.current(job())


def test_notification_adapter_requires_explicit_sent_timestamp():
    def handler(request):
        assert request.method == "POST"
        assert request.headers.get("X-API-Key") == "router-only"
        assert "X-N8N-API-KEY" not in request.headers
        if request.url.path == "/router":
            return httpx.Response(200, json={"accepted": True})
        assert request.url.path == "/ledger"
        payload = json.loads(request.content)
        assert payload == {
            "client_id": str(CLIENT_ID),
            "environment": "sandbox",
            "notification_scope_key": "scope",
        }
        return httpx.Response(200, json={
            "result_type": "notification_ledger.last_sent.v1",
            "last_notified_at": NOW.isoformat(),
        })

    with (
        httpx.Client(
            headers={"X-API-Key": "router-only"},
            transport=httpx.MockTransport(handler),
        ) as ledger_client,
        httpx.Client(
            headers={"X-API-Key": "router-only"},
            transport=httpx.MockTransport(handler),
        ) as router_client,
    ):
        adapter = NotificationRouterAdapter(
            ledger_client,
            router_client,
            ledger_url="http://n8n.local/ledger",
            router_url="http://n8n.local/router",
        )
        adapter.send({"test": True})
        assert adapter.last_sent_at(
            client_id=CLIENT_ID,
            environment="sandbox",
            recipient="D0B3LSR4C1Y",
            scope="scope",
        ) == NOW


def test_notification_adapter_fails_closed_on_missing_result():
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"rows": []}))
    ) as ledger_client, httpx.Client() as router_client:
        adapter = NotificationRouterAdapter(
            ledger_client,
            router_client,
            ledger_url="http://n8n.local/ledger",
            router_url="http://n8n.local/router",
        )
        with pytest.raises(ValueError, match="ledger response"):
            adapter.last_sent_at(
                client_id=CLIENT_ID,
                environment="sandbox",
                recipient="D0B3LSR4C1Y",
                scope="scope",
            )


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(200, json={"result_type": "notification_ledger.last_sent.v1", "last_notified_at": None}), None),
        (httpx.Response(503, json={"error": "unavailable"}), "http_error"),
        (httpx.Response(200, json={"result_type": "notification_ledger.last_sent.v1", "last_notified_at": "2026-10-22T12:00:00"}), "timestamp_error"),
    ],
)
def test_notification_lookup_null_or_failure(response, expected):
    with httpx.Client(
        headers={"X-API-Key": "router-only"},
        transport=httpx.MockTransport(lambda _: response),
    ) as ledger_client, httpx.Client() as router_client:
        adapter = NotificationRouterAdapter(
            ledger_client,
            router_client,
            ledger_url="http://n8n.local/ledger",
            router_url="http://n8n.local/router",
        )
        lookup = lambda: adapter.last_sent_at(
            client_id=CLIENT_ID,
            environment="sandbox",
            recipient="D0B3LSR4C1Y",
            scope=None,
        )
        if expected == "http_error":
            with pytest.raises(httpx.HTTPStatusError):
                lookup()
        elif expected == "timestamp_error":
            with pytest.raises(ValueError, match="timezone"):
                lookup()
        else:
            assert lookup() is None
