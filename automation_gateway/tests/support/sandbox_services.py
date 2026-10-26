"""Local-only QBO and notification stand-ins; never use real credentials."""

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI()
CLIENT_ID = "477751f2-1142-4283-a3c0-387f8aa45fbd"
state = {"is_connected": True, "connection_checked_at": "2026-10-20T12:00:00+00:00"}
deliveries = {}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/clients")
def list_clients(summary: bool = False):
    if not summary:
        raise HTTPException(400, "summary=true is required")
    return [{"id": CLIENT_ID, "status": "active", "environments": ["sandbox"]}]


@app.get("/qbo/{client_id}/companyinfo")
def company_info(client_id: str, environment: str):
    if client_id != CLIENT_ID or environment != "sandbox":
        raise HTTPException(404, "Sandbox credential not found")
    return JSONResponse(
        status_code=401,
        content={"code": 401, "details": {"provider": "intuit", "oauth_error": "invalid_grant"}},
    )


@app.put("/clients/{client_id}/connection-status")
async def update_status(client_id: str, request: Request):
    if client_id != CLIENT_ID:
        raise HTTPException(404, "Sandbox client not found")
    data = await request.json()
    if data.get("environment") != "sandbox":
        raise HTTPException(404, "Sandbox credential not found")
    checked_at = datetime.fromisoformat(data["checked_at"])
    previous = datetime.fromisoformat(state["connection_checked_at"])
    if checked_at > previous:
        state.update(
            is_connected=data["is_connected"],
            connection_checked_at=checked_at.astimezone(UTC).isoformat(),
        )
        outcome = "updated"
    elif checked_at == previous and state["is_connected"] == data["is_connected"]:
        outcome = "duplicate"
    else:
        outcome = "stale"
    return {"outcome": outcome, "applied": outcome == "updated"}


@app.get("/clients/{client_id}")
def client_detail(client_id: str):
    if client_id != CLIENT_ID:
        raise HTTPException(404, "Sandbox client not found")
    return {"name": "ACME Sandbox", "credentials": [{"environment": "sandbox", **state}]}


@app.post("/ledger")
async def delivery_lookup(request: Request):
    data = await request.json()
    if request.headers.get("X-API-Key") != "local-sandbox-test-only":
        raise HTTPException(403, "Invalid webhook key")
    if set(data) - {"client_id", "environment", "notification_scope_key"}:
        raise HTTPException(400, "Unexpected lookup field")
    matching = [
        row["notified_at"]
        for row in deliveries.values()
        if row["status"] == "sent"
        and row["channel"] == "slack"
        and row["recipient"] == "D0B3LSR4C1Y"
        and row["client_id"] == data["client_id"]
        and row["environment"] == data["environment"]
        and ("notification_scope_key" not in data or row["notification_scope_key"] == data["notification_scope_key"])
    ]
    return {"result_type": "notification_ledger.last_sent.v1", "last_notified_at": max(matching, default=None)}


@app.post("/router")
async def router(request: Request):
    data = await request.json()
    request_id = data["execution"]["request_id"]
    if request_id not in deliveries:
        deliveries[request_id] = {
            "status": "sent",
            "channel": "slack",
            "client_id": data["entity"]["client_id"],
            "environment": data["entity"]["environment"],
            "recipient": data["context"]["notification_recipient"],
            "notification_scope_key": data["context"]["communication"]["metadata"]["notification_scope_key"],
            "notified_at": datetime.now(UTC).isoformat(),
        }
    return {"status": "sent"}


@app.get("/sandbox-state")
def sandbox_state():
    return {"connection": state, "deliveries": len(deliveries)}
