# healthkey-etl integration

fhir-importers integrates with healthkey-etl through two channels:

1. **Airflow REST API** — fires the `fhir_extract` DAG on user-initiated events.
2. **Shared Postgres** — `mychart_connections` rows that healthkey-etl reads + updates.

The shared-DB exception is justified in [`DATA_FLOW.md`](DATA_FLOW.md). End-to-end data flows live in [`DATA_FLOW.md`](DATA_FLOW.md).

## DAG trigger

`BaseAirflowClient.create_dag_run(dag_id="fhir_extract", conf=…)` posts to Airflow's REST API. Two trigger sites with different error policies:

- **From `/auth/finish`**: best-effort. A failed trigger SHALL NOT roll back the persisted connection; the user re-triggers via `/connections/{alias}/sync`. Implementation logs and swallows the exception.
- **From `/sync`**: bubbles Airflow errors back to the caller as 502 — the user pressed the button expecting a response.

The DAG id is hardcoded — no per-call DAG selection.

## /sync handler

1. Verify Firebase JWT; capture `user_uid`.
2. Existence check on `mychart_connections` for `(user_uid, alias)`. 404 if missing or wrong user.
3. Fire DAG trigger with conf `{user_uid, organization_alias, epic_patient_id}`; `epic_patient_id` comes from the stored connection.
4. Return `{organization_alias, dag_run_id}`.

Per [`DATA_FLOW.md`](DATA_FLOW.md), the conf SHALL also include `trace_id`. Not yet wired in code; see [`observability.md`](observability.md).

## Shared-DB coupling

fhir-importers is the sole writer for `mychart_connections`. healthkey-etl reads tokens, refreshes them under a row-level lock ([`DATA_FLOW.md`](DATA_FLOW.md)), and writes back `last_synced_at`. From this side:

- Schema changes (Alembic migrations) SHALL ship to fhir-importers before healthkey-etl code that depends on them.
- New columns SHALL match healthkey-etl's repository expectations — coordinate ahead of merge.
- The Fernet key (`TOKEN_ENCRYPTION_KEY`) SHALL be identical across both services so refresh writes round-trip the cipher cleanly.
- A `needs_reauth` status column (when added) SHALL be writable by healthkey-etl on Epic `invalid_grant`; fhir-importers SHALL surface it on the `GET /epic/connections` listing.
