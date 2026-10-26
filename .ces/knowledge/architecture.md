# Architecture

FastAPI exposes a public `/health` route and an authenticated generic `POST /v1/jobs` endpoint. The route validates a versioned envelope and submits it through the `JobQueue` port. The Redis adapter routes by `kind` to a configured Redis List and uses one Lua operation to check the event ID, prepend the envelope for FIFO worker consumption, and set a TTL-based deduplication key. Payload contents are opaque to the gateway. Automation Gateway does not access PostgreSQL directly.

The separate single-consumer automation worker moves the oldest pending job to a processing List, resumes unfinished work, and records per-event checkpoints in Redis. Transient failures enter a per-client/environment retry List with due times in a Redis sorted set; subsequent events for that target wait in the same lane while other targets continue. Permanently missing QBO targets and status conflicts enter a recoverable dead-letter List. Its QBO connection handler alone calls QBO Gateway's existing status endpoint, verifies the stored state, and consults n8n's confirmed-delivery ledger before invoking the Notification Router. The gateway itself has no QBO or n8n dependency. The worker requires an explicitly verified router rule before startup; scaling beyond one replica requires additional per-target concurrency control.

The worker uses a separate HTTP client for QBO Gateway and authenticated HTTP clients for n8n lookup and dispatch. Both n8n webhooks use the same dedicated Header Auth credential; QBO credentials are never sent to n8n. The Router has published `POST /webhook/automation/notification-router/v1` for delivery and `POST /webhook/automation/notification-ledger/last-sent/v1` for read-only confirmed-delivery lookup. The lookup fixes channel and recipient to the approved Slack DM and returns only the latest timestamp or null; the worker can additionally filter by episode scope. Neither the worker nor Airflow uses the n8n Data Tables API directly. The Router's delivery adapter limits webhook input to QBO disconnection for the approved Slack DM before entering shared routing logic. A fictional sandbox event confirmed one Slack delivery and retry suppression; the lookup returned the recorded timestamp and rejected an unauthenticated request with 403. The worker remains undeployed outside tests.

## Evidence

- `README.md`
- `automation_gateway/app.py`
- `automation_gateway/api/jobs.py`
- `automation_gateway/api/dependencies.py`
- `automation_gateway/application/ports.py`
- `automation_gateway/infrastructure/redis_job_queue.py`
- `automation_worker/runner.py`
- `automation_worker/connection.py`
- `automation_gateway/tests/test_worker_queue_order.py`
