# Conventions

`PUT /v1/connections/{client_id}/status` requires `X-API-Key` and a UUID client ID. Requests forbid extra fields; `environment` is `prod` or `sandbox`, `is_connected` is a strict JSON boolean, `checked_at` includes a timezone, and `correlation_id` is a UUID. Settings load from environment variables or `.env` and are cached.

## Evidence

- `README.md`
- `automation_gateway/schemas/connection_status.py`
- `automation_gateway/api/dependencies.py`
- `automation_gateway/core/config.py`
