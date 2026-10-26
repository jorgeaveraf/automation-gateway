# Glossary

- **Job envelope:** Versioned job metadata (`event_id`, `kind`) and opaque JSON payload submitted to the queue.
- **Event ID:** UUID used for enqueue idempotency within the configured TTL.
- **Job kind:** Versioned routing key mapped to a Redis List key by configuration.

## Evidence

- `README.md`
- `automation_gateway/application/ports.py`
- `automation_gateway/schemas/jobs.py`
