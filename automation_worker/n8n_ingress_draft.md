# Notification Router webhook ingress — published

The existing n8n Notification Router retains its Execute Workflow entry.
Version `830f097e-dc53-4836-8dd3-2072f823152b` is published as of
2026-10-23 and contains:

1. A `POST` Webhook at path `automation/notification-router/v1`, with `Header
   Auth` using the dedicated `HQ Automation Worker — Notification Router`
   credential and header `X-API-Key`. No QBO or Postmark credential is reused.
2. `Adapt Webhook request`, which unwraps the JSON `body` to the existing
   `notification_router.request` contract. Before routing it, the adapter
   requires the QBO disconnect event, the Automation Worker source, the
   `QBO_CONNECTION_DISCONNECTED` code, Slack channel, and the approved DM
   `D0B3LSR4C1Y` in all recipient fields. It then sets
   `context._notification_router_ingress = "webhook"`. Other events or
   destinations fail before rule selection or provider delivery.
3. The adapter and the original `Receive Notification Event` both connect to
   `Validate Notification Contract`, preserving the existing downstream logic.
4. After suppression, `Webhook? — suppressed` returns the normalized
   suppression result only to HTTP callers. After provider delivery and
   Coordinator commit, `Webhook? — sent` responds from the committed state.
   Non-webhook callers end through the original output paths.

The Webhook's response mode is `Using 'Respond to Webhook' Node`, not
`Immediately`. Its test URL is
`https://fnan8n.headquarters.co/webhook-test/automation/notification-router/v1`.
The active production URL is
`https://fnan8n.headquarters.co/webhook/automation/notification-router/v1`.
The QBO-specific rule and template in
`n8n_qbo_disconnect_draft.json` are installed as Data Table rows 43 and 51,
respectively. The rule's only action targets Slack DM `D0B3LSR4C1Y`.
The Gmail draft branches do not yet have an HTTP
response, so the ingress remains restricted to the intended QBO/Slack event.
A missing `Respond to Webhook` execution may otherwise
produce a generic HTTP 200 without a delivery result.

The worker remains undeployed. Set `NOTIFICATION_ROUTER_URL` to the production
URL and `NOTIFICATION_ROUTER_RULE_READY=true` only in a validated worker
environment with the remaining required secrets and dependencies configured.
`NOTIFICATION_ROUTER_API_KEY` must match the dedicated Header Auth credential.
The worker queries the read-only ledger webhook with the same key before and
after dispatch, and verifies a `sent` delivery timestamp after dispatch. HTTP
2xx alone never completes the job. Do not commit the secret to this repository.

The separate `POST /webhook/automation/notification-ledger/last-sent/v1`
branch accepts `client_id`, `environment`, and optional
`notification_scope_key`. It fixes the lookup to confirmed Slack deliveries
for `D0B3LSR4C1Y` and responds with
`{"result_type":"notification_ledger.last_sent.v1","last_notified_at":<UTC timestamp or null>}`.
It does not call a delivery provider, expose table rows, or accept a caller-
selected recipient. Any lookup or parsing error fails the workflow rather than
reporting `null`. Airflow omits scope for its 48-hour hint; the worker uses
scope to confirm a specific disconnection episode.
Manual lookups against the draft returned the latest timestamp, a scoped
timestamp, and `null` for an absent scope/client. The published URL returned
the existing fictional client's timestamp and `null` for an absent fictional
client; no-key access returned 403. Execution 132890 ran only the five lookup
nodes, with no Slack or Gmail delivery node.

Controlled ingress checks on the unpublished test URL: a POST without the
Header Auth key returned 403 without executing the workflow. A POST with the
key and an empty JSON body returned 500 during full-workflow execution, before
any notification node. The n8n trigger-only “Listen for test event” mode
returned 200 for the same body because it did not execute downstream nodes;
it is not a delivery test.

On 2026-10-23, a full editor execution with fake client ID
`00000000-0000-4000-8000-000000000099` and request ID suffix
`controlled-test-20261023:slack:D0B3LSR4C1Y:initial` returned HTTP 200,
`delivery_status=sent`, and `committed=true`. Delivery ledger row 72 records
one Slack message with `channel_id=D0B3LSR4C1Y`. A second full execution with
the same request ID returned HTTP 200 and `delivery_status=suppressed`; no
second Slack delivery was requested. No real QBO client was read or changed.

The workflow already had pinned outputs for `Load Candidate Notification
Rules`, `Load Template for Delivery Action`, and `Coordinator — Decide Deliver
or Suppress`. These pins initially masked the new live Data Table rows during
the controlled test. Their original JSON was preserved, the pins were
temporarily removed for the full executions, and all three original pins were
restored afterward. For a future editor retest, temporarily unpin these
nodes, then restore their original data; otherwise the QBO path will appear
to fail even when the live rule and template are valid.

After publication, a production-URL request without `X-API-Key` returned 403.
One request for fictional sandbox client
`00000000-0000-4000-8000-000000000099` returned `delivery_status=sent` and
`committed=true`; delivery row 79 records exactly one Slack message to
`D0B3LSR4C1Y` (router execution 132779). Repeating the same request returned
`delivery_status=suppressed` and retained the same provider message ID. No QBO
client was queried or changed, and the worker and periodic monitor were not
started.
