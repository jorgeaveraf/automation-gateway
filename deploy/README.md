# Automation Gateway deployment preparation

These files prepare a parallel, loopback-only Automation Gateway deployment. They do not replace the legacy `ingestion-gateway` container or change Nginx.

## Intended VPS layout

```text
/root/automations/automation-gateway/
  docker-compose.production.yml
  .env                 # secrets, mode 600, never committed
  .release.env         # current immutable image, managed by deploy script

/usr/local/sbin/deploy-automation-gateway
```

The initial host binding is `127.0.0.1:8002`. Port `8001` remains available to the legacy service until the separate cutover iteration. The container reaches QBO Gateway through `host.docker.internal:8000`; the Compose file maps that name to the Linux host gateway.

## One-time server preparation

Do not run these steps until the local artifacts and deployment plan have been approved.

1. Create `/root/automations/automation-gateway` with root ownership and mode `700`.
2. Copy `docker-compose.production.yml` into that directory.
3. Create `.env` from `automation-gateway.env.example`, insert production secrets, and set mode `600`.
4. Install `deploy-automation-gateway` at `/usr/local/sbin/deploy-automation-gateway`, owned by root and executable.
5. Ensure root can pull the private GHCR image without placing a registry token in this repository.
6. Configure the CI deployment identity with narrowly scoped passwordless sudo for this single script.
7. Configure the GitHub `production` environment and its required reviewer plus `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, and pinned `VPS_KNOWN_HOSTS` secrets.

## Deployment behavior

The script accepts only a lowercase 40-character Git SHA, pulls the corresponding immutable image, writes `.release.env` atomically, recreates only the `automation-gateway` service, and waits for the image healthcheck plus loopback `/health` response.

Before pulling an image, it also requires `.env` mode `600` and non-empty `AUTOMATION_GATEWAY_API_KEY`, `QBO_GATEWAY_BASE_URL`, and `QBO_GATEWAY_API_KEY` values. Secret values are never printed.

If validation fails, it restores the previously recorded immutable image. On a failed first deployment, it removes only the new Automation Gateway container. It never operates on the legacy Compose project, QBO Gateway, PostgreSQL, Nginx, or Airflow.

## Local validation

Use placeholder values only:

```bash
AUTOMATION_IMAGE=ghcr.io/jorgeaveraf/automation-gateway:0000000000000000000000000000000000000000 \
AUTOMATION_GATEWAY_ENV_FILE=automation-gateway.env.example \
docker compose --env-file deploy/automation-gateway.env.example \
  -f deploy/docker-compose.production.yml config --quiet

bash -n deploy/deploy-automation-gateway
```
