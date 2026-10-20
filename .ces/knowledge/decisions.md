# Decisions

- **Explicit documentation — current:** Automation Gateway publishes validated connection status to QBO Gateway over HTTP; QBO Gateway remains responsible for PostgreSQL persistence.
- **Explicit documentation — current:** `/health` is public and does not check external dependencies.
- **Inference from code — current:** The API, use case, and publisher port separate request handling from outbound publication.
- **Explicit user decision — current:** Connection status is boolean. A successful CompanyInfo check maps to `is_connected=true`; after Airflow exhausts retries, an unsuccessful check maps to `is_connected=false`. There is no `unknown` state.
- **Explicit user decision — current:** Automation Gateway evolves from the existing Ingestion Gateway repository; it is not a second permanent gateway repository. Production replacement will occur only after separate local validation and deployment preparation.
- **Implementation decision — current:** CI validation and production delivery are separate. Deployment is manual, restricted to `main`, and cannot succeed until the new VPS deployment script is deliberately installed.
- **Implementation decision — deployment preparation:** The first Automation Gateway deployment binds only to `127.0.0.1:8002` and runs beside the legacy service for validation. It does not change Nginx or claim legacy port 8001.
- **Implementation decision — deployment preparation:** Releases use immutable commit-SHA image tags. Failed health validation restores the previously recorded image; a failed first deployment removes only the new service.
- **Implementation decision — deployment preparation:** GitHub and the host deployment script serialize production deployments. The active release record changes only after the candidate image passes health validation.

## Evidence

- `README.md`
- `automation_gateway/app.py`
- `automation_gateway/api/connection_status.py`
- `automation_gateway/application/publish_connection_status.py`
- `automation_gateway/application/ports.py`
- `automation_gateway/infrastructure/qbo_gateway_publisher.py`
- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml`
- `deploy/docker-compose.production.yml`
- `deploy/deploy-automation-gateway`
