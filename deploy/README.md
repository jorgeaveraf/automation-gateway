# Gateway v2 production rollout

The existing `automation-gateway` project stays on port 8002 while this release starts a separate `automation-gateway-v2` project on loopback port 8003. Its Compose stack starts Redis with an AOF volume, the API, and one worker. The image carries the exact production Compose file used by the deploy script. No QBO Gateway, QBO database, Nginx, or old Gateway service is modified.

On the first v2 release, the script preserves the old Compose as `docker-compose.legacy.yml` and its image tag as `.release.legacy.env`. These allow an explicit restart of the old project during the Airflow transition.

## One-time preparation before merging to main

The VPS already has Docker Compose, the `deploy` account, GHCR pull access, and sudo permission for `/usr/local/sbin/deploy-automation-gateway`. Preserve them.

1. Install the reviewed `deploy/deploy-automation-gateway` as that existing root-owned executable. The new script replaces the old implementation at the same path, so sudoers need no change.
2. Keep `/root/automations/automation-gateway/.env` root-owned, mode 600, with `AUTOMATION_GATEWAY_API_KEY` and `REDIS_JOB_QUEUES`. Its Redis URL is overridden by Compose to the private `redis` service.
3. Create `/root/automations/automation-gateway/.env.worker` root-owned, mode 600. Supply the keys in `.env.worker.example`, production QBO and notification URLs and credentials, and set `NOTIFICATION_ROUTER_RULE_READY=true` only after the router rule is verified. Do not commit or print values.
4. Confirm port 8003 and the project name `automation-gateway-v2` are unused. The first merge to `main` installs its Compose from the API image. There is no separate Compose copy step.
5. Ensure the GitHub `production` environment has `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, and pinned `VPS_KNOWN_HOSTS` secrets. Configure no manual environment reviewer if main is to deploy automatically. Require the CI job on protected main.

`develop` and pull requests run CI only. A successful push to `main` builds and publishes API and worker images tagged with the same commit SHA, then deploys them. The script validates secrets, pulls both images, extracts and validates Compose, starts Redis/API/worker, checks health, and records the release. On failure it restores prior Compose and images. The first v2 failure removes only the v2 stack; its Redis volume remains.

Only after Gateway v2 is healthy should Airflow switch its private network and base URL. Keep the old Gateway until the Airflow cutover is validated. Do not delete the Redis volume during rollback.
