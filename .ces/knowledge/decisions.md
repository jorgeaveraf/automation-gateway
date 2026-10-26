# Decisions

- **Explicit implementation decision — current:** Automation Gateway accepts generic versioned jobs and transports them through Redis Lists; Redis Streams and Pub/Sub are not used as the transport.
- **Explicit implementation decision — current:** `event_id` deduplication and Redis List append are performed atomically by Lua, with a configurable TTL (default 30 days). Both newly accepted and duplicate submissions return HTTP 202 after Redis confirms the operation.
- **Explicit implementation decision — current:** Queue selection uses configured `kind` to List-key mapping; the gateway does not inspect job payloads.
- **Explicit documentation — current:** `/health` is public and does not check external dependencies.
- **Explicit user decision — current:** Automation Gateway evolves from the existing Ingestion Gateway repository; it is not a second permanent gateway repository. Production replacement will occur only after separate local validation and deployment preparation.
- **Implementation decision — current:** CI validation and production delivery are separate. Deployment is manual, restricted to `main`, and cannot succeed until the new VPS deployment script is deliberately installed.
- **Implementation decision — deployment preparation:** The first Automation Gateway deployment binds only to `127.0.0.1:8002` and runs beside the legacy service for validation. It does not change Nginx or claim legacy port 8001.
- **Implementation decision — notification webhooks:** The reusable n8n Notification Router retains its Execute Workflow entry and exposes authenticated `POST automation/notification-router/v1` delivery and `POST automation/notification-ledger/last-sent/v1` read-only lookup paths. Both use the same dedicated `X-API-Key` Header Auth credential. The lookup fixes Slack DM destination server-side, returns only a confirmed timestamp or null, and fails closed on errors. Airflow and the worker no longer require n8n Data Tables API credentials.
- **Implementation decision — deployment preparation:** Releases use immutable commit-SHA image tags. Failed health validation restores the previously recorded image; a failed first deployment removes only the new service.
- **Implementation decision — deployment preparation:** GitHub and the host deployment script serialize production deployments. The active release record changes only after the candidate image passes health validation.

## Evidence

- `README.md`
- `automation_gateway/app.py`
- `automation_gateway/api/jobs.py`
- `automation_gateway/application/ports.py`
- `automation_gateway/infrastructure/redis_job_queue.py`
- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml`
- `deploy/docker-compose.production.yml`
- `deploy/deploy-automation-gateway`
