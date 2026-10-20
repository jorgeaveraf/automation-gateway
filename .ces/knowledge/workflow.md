# Workflow

Run locally with `pip install -r requirements.txt` and `uvicorn automation_gateway.app:app --reload --port 8000`; run tests with `pytest`. Docker Compose builds the service and maps loopback-only host port 8001 to container port 8000. The image runs as a non-root user and defines a `/health`-based container health check.

CI validates application import, tests, and image build for pull requests and pushes to `develop` or `main`; it does not publish or deploy. A separate manually dispatched workflow, restricted to `main`, publishes an immutable SHA-tagged image and gates deployment through the `production` environment. SSH host verification uses a pinned `VPS_KNOWN_HOSTS` secret. The expected `/usr/local/sbin/deploy-automation-gateway` server-side script does not currently exist, so production delivery is intentionally not operational yet.

Local Docker integration testing binds published ports to `127.0.0.1`. The test-only ASGI app overrides the outbound publisher with a no-op fake so the Airflow HTTP client can exercise authenticated `true` and `false` status publications without calling QBO Gateway or another external service.

## Evidence

- `README.md`
- `requirements.txt`
- `Dockerfile`
- `docker-compose.yml`
- `automation_gateway/tests/integration_app.py`
- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml`
