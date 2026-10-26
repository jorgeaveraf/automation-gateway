# Known-Errors

- **OPEN, configuration dependent:** Without Redis URL or a configured kind-to-List routing map, an authenticated job request returns HTTP 503, `Redis job queue is not configured`.
- **OPEN, dependency dependent:** Redis failure before confirmation returns HTTP 503; no successful acceptance response is sent.
- **OPEN, configuration dependent:** A kind without a configured List key returns HTTP 422.
- **OPEN, configuration dependent:** If the API key setting is absent, the protected route returns HTTP 503, `Service authentication is not configured`.

## Evidence

- `README.md`
- `automation_gateway/api/dependencies.py`
- `automation_gateway/api/jobs.py`
- `automation_gateway/infrastructure/redis_job_queue.py`
- `automation_gateway/tests/test_automation_gateway.py`
