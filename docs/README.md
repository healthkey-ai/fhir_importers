# fhir-importers — System Design

**Status**: requirements / target state.
**Treat this directory as the Definition of Done.** Grep for `SHALL`/`SHOULD`/`MUST` across these files for testable contracts; anything in the code that doesn't satisfy one is delta.

## Responsibility

Per [`DATA_FLOW.md`](DATA_FLOW.md): fhir-importers runs the Epic OAuth handshake, persists encrypted tokens, exposes connection management UX as a Module Federation remote, and triggers the `fhir_extract` DAG on connect / re-sync.

**State owned**: `mychart_connections` table (sole writer); transient OAuth state in Redis with TTL.

**SHALL NOT**: fetch FHIR resources, parse FHIR, talk to ctomop.

## Topics

| File | What's in it |
|---|---|
| [DATA_FLOW.md](DATA_FLOW.md) | **Start here.** End-to-end data flow for the FHIR patient data fetching feature: participants, OAuth + import sequences, cross-service contracts |
| [api.md](api.md) | HTTP surface — framework, middleware, error shapes, auth boundary |
| [token-management.md](token-management.md) | `mychart_connections` schema, identity persistence, OAuth handlers, encryption-at-rest, private-key JWT material |
| [healthkey-etl-integration.md](healthkey-etl-integration.md) | DAG trigger via Airflow, `/sync` handler, shared-DB coupling |
| [frontend-remote.md](frontend-remote.md) | Module Federation 2.0 build, exposed components, ht-phr host contract |
| [deployment.md](deployment.md) | Docker image, compose services, env vars |
| [observability.md](observability.md) | `trace_id` propagation through fhir-importers |

## Related docs (parent directory)

- [`../openapi.yaml`](../openapi.yaml) — HTTP contract (paths, request/response shapes, status codes)
- [`../healthkey-etl/`](../healthkey-etl/README.md) — sibling service design
