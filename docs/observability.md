# Observability

Per [`DATA_FLOW.md`](DATA_FLOW.md): fhir-importers SHALL include `trace_id` in every structured log line emitted while handling a user-initiated flow.

## trace_id generation points

- `POST /epic/auth/start` — generated at handler entry and stored alongside the OAuth state in Redis (as a field on `PendingState`); carried through the Epic redirect and recovered by `/auth/finish` when the state is GETDEL'd.
- `POST /epic/connections/{alias}/sync` — generated at handler entry; not stored anywhere (the trigger fires immediately).

## Propagation

Once generated, the id SHALL be:

- Logged on every structured log line for the remainder of the request handler (via a context-local field on the logger).
- Passed as a `conf` field on every `fhir_extract` DAG trigger fired during the request — see [`healthkey-etl-integration.md`](healthkey-etl-integration.md).
- Returned to the caller on `/auth/start` and `/connections/{alias}/sync` response bodies so the host SPA can join its own logs to the backend's.

## Out of scope

Service-internal observability beyond the cross-service `trace_id` — metrics, dashboards, alerting thresholds, log shipping — is not specified by this design document. Operators choose what fits the deployment.
