# Automation Gateway

FastAPI service that accepts versioned automation jobs and enqueues them in Redis Lists.

The gateway validates the generic job envelope, routes by `kind`, and never interprets the payload. Redis atomically deduplicates `event_id` and appends new jobs to a Redis List; the gateway does not access PostgreSQL or publish through Redis Streams or Pub/Sub.

## Requirements

- Python 3.11+
- Docker and Docker Compose (optional)

## Local configuration

Copy `.env.example` to `.env` and use local-only values. The protected endpoint requires `AUTOMATION_GATEWAY_API_KEY`, `REDIS_URL`, and `REDIS_JOB_QUEUES`. `JOB_DEDUPLICATION_TTL_SECONDS` defaults to 30 days.

## Run locally

```bash
pip install -r requirements.txt
uvicorn automation_gateway.app:app --reload --port 8000
```

## API

### `GET /health`

Public liveness endpoint. It does not check external dependencies.

### `POST /v1/jobs`

Accepts a versioned job envelope and requires `X-API-Key`. `event_id` is a UUID, `kind` identifies the job version, and `payload` is an opaque JSON object. Redis List routing is configured as a JSON object mapping kinds to queue keys.

```json
{
  "event_id": "070b2e37-aa28-4911-b2b2-e493678d38f5",
  "kind": "qbo.connection_checked.v1",
  "payload": {
    "client_id": "477751f2-1142-4283-a3c0-387f8aa45fbd",
    "provider": "qbo",
    "environment": "sandbox",
    "is_connected": false,
    "checked_at": "2026-10-22T12:00:00Z",
    "correlation_id": "7ac383c5-7d11-488f-8ba8-11bd2c02023d",
    "notification": {"candidate": true, "observed_previous_connected": true}
  }
}
```

Both a newly enqueued event and a duplicate return `202` with `accepted: true`; `duplicate` distinguishes the cases. A response is sent only after Redis confirms the atomic operation. Unconfigured or unavailable Redis returns `503`; an unmapped kind returns `422`.

## Tests

```bash
pytest
```

Unit tests use a fake Redis client and require no Redis service. The test-only ASGI app can accept local Docker jobs without an external queue.

## Local Docker

```bash
docker compose up --build
```

The local Compose file binds the service only to `127.0.0.1:8001`. The image runs as an unprivileged user and exposes a container health check backed by `GET /health`. No shared filesystem volume is required.

The separate `automation-worker` service consumes one Redis List in FIFO order
with an atomic pending-to-processing move. It resumes unfinished jobs after restart,
defers transient failures to a target-specific retry lane so other clients can
continue, and preserves the order of events for each client and environment.
Retry lanes use Redis Lists plus a sorted set of due times; they do not use Redis
Streams. A permanently missing QBO client or credential, or an equal-timestamp
status conflict, goes to the recoverable `:dead` List instead of retrying forever.
Inspect dead-letter jobs and correct their cause before republishing them as a
new event through the Gateway; they are never replayed automatically. Reuse of
the original event ID is subject to the Gateway's idempotency window.
The worker writes the
status through QBO Gateway's existing endpoint, re-checks the saved value, and
only then evaluates notification eligibility. It queries a sent-only n8n ledger
adapter before and after calling the Notification Router. An HTTP success alone
never counts as a delivered Slack notification. One worker replica is supported;
do not scale this service without adding per-target concurrency control.

Set `.env.worker` from `.env.worker.example` for local use. The worker refuses to
start unless `NOTIFICATION_ROUTER_RULE_READY=true`; set that only after the
dedicated rule and template have been verified through controlled editor tests
and explicitly activated. Local Docker tests use the included mock, not a real
client or the live n8n endpoint.

`NOTIFICATION_SLACK_DESTINATION_ID` is the DM conversation ID, not the Slack
user ID. The worker sends it as a Slack `channel` destination and looks up
deliveries using the same recipient value. `NOTIFICATION_SLACK_ADDITIONAL_USER_ID`
can override the additional Slack user ID (`U03PQMKUR6J` by default) for QBO
disconnect alerts only.
The worker sends separate requests and checks the 48-hour ledger independently
for each destination. The current DM ID in the existing delivery table is
`D0B3LSR4C1Y` for `@jorge.vera`; keep both values configurable.

The isolated Docker contract test uses only the ACME sandbox mock and no real
external services:

```bash
docker compose -f automation_gateway/tests/support/docker-compose.worker.yml up -d --build
# POST a sandbox job to 127.0.0.1:18092/v1/jobs, then inspect
# 127.0.0.1:18091/sandbox-state
docker compose -f automation_gateway/tests/support/docker-compose.worker.yml down
```

The worker and Airflow read confirmed `status=sent` deliveries through the
Notification Router's authenticated `POST
/webhook/automation/notification-ledger/last-sent/v1`. Neither client needs
an n8n Data Tables API key. The published QBO webhook accepts either approved
recipient for QBO disconnect requests and defaults to the existing DM for
legacy lookups. It returns only
`last_notified_at` (or `null`); the worker additionally
filters by episode scope. Both clients reject malformed responses.
The router
webhook must accept the existing `notification_router.request` body, commit
its delivery row, and persist `notification_scope_key` in a nullable column or
metadata. These n8n configuration steps are prerequisites, not changes to QBO
Gateway. The QBO rule and template are captured in
`automation_worker/n8n_qbo_disconnect_draft.json` and installed as active n8n
Data Table rows 43 and 51. A controlled full-workflow test sent one Slack DM
to `D0B3LSR4C1Y`; retrying the same request was suppressed. The three
pre-existing pinned outputs were restored afterward. On 2026-10-23 the Router
webhook was published at `POST /webhook/automation/notification-router/v1` with a
dedicated `X-API-Key` Header Auth credential; its published version is
`830f097e-dc53-4836-8dd3-2072f823152b`. A production-URL test with a
fictitious sandbox client returned `sent` and `committed=true`; delivery row 79
records one Slack message to `D0B3LSR4C1Y`. The same request was suppressed on
retry, and a request without the key returned 403. The ingress and remaining
worker validation gates are documented in
`automation_worker/n8n_ingress_draft.md`. Both n8n webhooks use the dedicated
`X-API-Key` Header Auth credential; no key is sent to QBO Gateway. The worker
remains undeployed; publishing the webhook did not enable periodic monitoring
or start the worker.

## Delivery workflows

The CI workflow runs application import validation, the test suite, and a container build for pull requests and pushes to `develop` or `main`. It does not publish images or deploy.

Production delivery is intentionally separate and manual. The deploy workflow can run only from `main`, publishes an immutable image tagged with the commit SHA, and gates the SSH deployment through the protected `production` environment. It requires the environment secrets `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, and a pinned `VPS_KNOWN_HOSTS`; it also expects `/usr/local/sbin/deploy-automation-gateway` to exist on the target host. That VPS script and environment setup are not part of this local iteration, so the workflow must not be run until the server-side deployment preparation is complete.

Version-controlled server preparation artifacts live in `deploy/`. They define a parallel loopback-only deployment on port `8002`, immutable SHA releases, health validation, and rollback without operating on the legacy Ingestion Gateway deployment.
