# Known-Errors

- **OPEN, configuration dependent:** Without QBO Gateway URL or admin API key, an authenticated status request returns HTTP 503, `Connection status publisher is not configured`; no external publication occurs.
- **OPEN, dependency dependent:** QBO Gateway transport or HTTP failures return 502 and outbound timeouts return 504.
- **OPEN, configuration dependent:** If the API key setting is absent, the protected route returns HTTP 503, `Service authentication is not configured`.

## Evidence

- `README.md`
- `automation_gateway/api/dependencies.py`
- `automation_gateway/api/connection_status.py`
- `automation_gateway/infrastructure/qbo_gateway_publisher.py`
- `automation_gateway/tests/test_automation_gateway.py`
