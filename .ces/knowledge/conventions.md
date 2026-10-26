# Conventions

`POST /v1/jobs` requires `X-API-Key` and a strict envelope with UUID `event_id`, non-empty versioned `kind`, and object-valued opaque JSON `payload`; extra top-level fields are forbidden. A successful queue write and an idempotent duplicate both return `202` with `accepted=true`; `duplicate` distinguishes them. Routing maps kinds to Redis List keys in `REDIS_JOB_QUEUES` JSON. Settings load from environment variables or `.env` and are cached.

## Evidence

- `README.md`
- `automation_gateway/schemas/jobs.py`
- `automation_gateway/api/dependencies.py`
- `automation_gateway/core/config.py`
