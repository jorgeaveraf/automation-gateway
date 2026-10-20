# Automation Gateway

FastAPI service that receives normalized results from automation systems and publishes QBO connection status through an explicit outbound port.

The current implementation forwards validated status updates to QBO Gateway. It does not access PostgreSQL directly and contains no n8n or production-specific integration.

## Requirements

- Python 3.11+
- Docker and Docker Compose (optional)

## Local configuration

Copy `.env.example` to `.env` and use local-only values. The protected endpoint requires `AUTOMATION_GATEWAY_API_KEY`. Outbound publication requires `QBO_GATEWAY_BASE_URL`, the QBO admin `QBO_GATEWAY_API_KEY`, and an optional `QBO_GATEWAY_TIMEOUT_SECONDS`.

## Run locally

```bash
pip install -r requirements.txt
uvicorn automation_gateway.app:app --reload --port 8000
```

## API

### `GET /health`

Public liveness endpoint. It does not check external dependencies.

### `PUT /v1/connections/{client_id}/status`

Receives the latest observed state for a client connection. It requires `X-API-Key`.

```json
{
  "provider": "qbo",
  "environment": "prod",
  "is_connected": true,
  "checked_at": "2026-09-25T15:30:00Z",
  "correlation_id": "7ac383c5-7d11-488f-8ba8-11bd2c02023d"
}
```

`is_connected` must be a JSON boolean. A successful QBO CompanyInfo check is published as `true`; a check that remains unsuccessful after Airflow exhausts its retries is published as `false`. Allowed environments are `prod` and `sandbox`.

The QBO publisher calls `PUT /clients/{client_id}/connection-status`. Missing publisher configuration returns `503`, QBO transport or HTTP failures return `502`, and timeouts return `504`.

## Tests

```bash
pytest
```

Unit tests use in-memory HTTP transports and make no external HTTP or database calls. The test-only ASGI app can accept local Docker publications without forwarding them.

## Local Docker

```bash
docker compose up --build
```

The local Compose file binds the service only to `127.0.0.1:8001`. The image runs as an unprivileged user and exposes a container health check backed by `GET /health`. No shared filesystem volume is required.

## Delivery workflows

The CI workflow runs application import validation, the test suite, and a container build for pull requests and pushes to `develop` or `main`. It does not publish images or deploy.

Production delivery is intentionally separate and manual. The deploy workflow can run only from `main`, publishes an immutable image tagged with the commit SHA, and gates the SSH deployment through the protected `production` environment. It requires the environment secrets `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, and a pinned `VPS_KNOWN_HOSTS`; it also expects `/usr/local/sbin/deploy-automation-gateway` to exist on the target host. That VPS script and environment setup are not part of this local iteration, so the workflow must not be run until the server-side deployment preparation is complete.

Version-controlled server preparation artifacts live in `deploy/`. They define a parallel loopback-only deployment on port `8002`, immutable SHA releases, health validation, and rollback without operating on the legacy Ingestion Gateway deployment.
