# Architecture

FastAPI exposes a public `/health` route and an authenticated connection-status route. The route validates input, calls `PublishConnectionStatus`, and delegates publication through the `ConnectionStatusPublisher` port. When QBO settings are present, the HTTP adapter publishes to QBO Gateway's connection-status endpoint; Automation Gateway does not access PostgreSQL directly.

## Evidence

- `README.md`
- `automation_gateway/app.py`
- `automation_gateway/api/connection_status.py`
- `automation_gateway/api/dependencies.py`
- `automation_gateway/application/publish_connection_status.py`
- `automation_gateway/application/ports.py`
- `automation_gateway/infrastructure/qbo_gateway_publisher.py`
