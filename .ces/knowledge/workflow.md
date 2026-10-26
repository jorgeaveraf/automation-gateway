# Workflow

Run locally with `pip install -r requirements.txt` and `uvicorn automation_gateway.app:app --reload --port 8000`; run tests with `pytest`. Docker Compose builds the service and maps loopback-only host port 8001 to container port 8000. The image runs as a non-root user and defines a `/health`-based container health check.

CI validates application import, tests, and both API/worker image builds on pull requests and pushes to `develop` or `main`. A successful push to `main` also publishes both immutable SHA-tagged images and deploys through the `production` environment. The prior manually dispatched workflow has been removed locally. SSH host verification uses pinned `VPS_KNOWN_HOSTS`. Branch protection for main remains a one-time GitHub setting before automatic deployment.

GitHub-maintained checkout and Python setup actions use their Node 24-compatible v7 releases.

Version-controlled production Compose is embedded in the API image and extracted by the deploy script. The new `automation-gateway-v2` project binds loopback port 8003 and starts Redis with AOF persistence, the API, and one worker. The existing port 8002 Gateway stays live until Airflow cutover. The script validates health and restores previous Compose and images on failure.

The deploy script requires root-owned `.env` and `.env.worker` with mode 600, validates Gateway and worker settings, and requires explicit `NOTIFICATION_ROUTER_RULE_READY=true`. Compose supplies the private Redis URL.

Local Docker integration testing binds published ports to `127.0.0.1`. The test-only ASGI app overrides the job queue with an in-memory fake. Unit tests use a fake Redis client and do not require a Redis service.

The Notification Router's QBO webhook is published. Its QBO rule and Slack template are active Data Table rows 43 and 51, but the automation worker remains undeployed. A controlled synthetic-client editor test on 2026-10-23 committed one Slack DM to `D0B3LSR4C1Y`; a repeat of the same request ID was suppressed. The three pre-existing n8n pinned outputs temporarily removed for this test were restored. See `automation_worker/n8n_ingress_draft.md` for the publication and production URL test evidence.

## Evidence

- `README.md`
- `requirements.txt`
- `Dockerfile`
- `docker-compose.yml`
- `automation_gateway/tests/integration_app.py`
- `automation_gateway/tests/test_redis_job_queue.py`
- `.github/workflows/ci.yml`
- `deploy/docker-compose.production.yml`
- `deploy/deploy-automation-gateway`
- `deploy/README.md`
- `automation_worker/n8n_ingress_draft.md`
