# Decisions

- **Explicit documentation — current:** Automation Gateway publishes validated connection status to QBO Gateway over HTTP; QBO Gateway remains responsible for PostgreSQL persistence.
- **Explicit documentation — current:** `/health` is public and does not check external dependencies.
- **Inference from code — current:** The API, use case, and publisher port separate request handling from outbound publication.
- **Explicit user decision — current:** Connection status is boolean. A successful CompanyInfo check maps to `is_connected=true`; after Airflow exhausts retries, an unsuccessful check maps to `is_connected=false`. There is no `unknown` state.
- **Explicit user decision — current:** Automation Gateway evolves from the existing Ingestion Gateway repository; it is not a second permanent gateway repository. Production replacement will occur only after separate local validation and deployment preparation.
- **Implementation decision — current:** CI validation and production delivery are separate. Deployment is manual, restricted to `main`, and cannot succeed until the new VPS deployment script is deliberately installed.

## Evidence

- `README.md`
- `automation_gateway/app.py`
- `automation_gateway/api/connection_status.py`
- `automation_gateway/application/publish_connection_status.py`
- `automation_gateway/application/ports.py`
- `automation_gateway/infrastructure/qbo_gateway_publisher.py`
- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml`
