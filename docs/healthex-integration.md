# HealthEx integration

[HealthEx](https://healthex.io) is a **patient-driven consent + data aggregation platform**. They handle the per-EHR fan-out (TEFCA via QHINs) and the patient identity/consent UI; we call a single FHIR endpoint and get a unified bundle.

**Status**: fhir-importers side implemented (org-JWT auth, Unique Link onboarding, status polling, `healthex_patient_links` table). healthkey-etl extract DAG not yet built. **End-to-end consent flow not yet executed against a real consenting patient** — verified via API probes + `test_healthex_flow.py` smoke harness.

Last verified against the live API on **2026-06-21**.

Sources:
- [docs.healthex.io — Overview](https://docs.healthex.io/) · [Key Concepts](https://docs.healthex.io/key-concepts/)
- [docs.healthex.io — Authentication](https://docs.healthex.io/authentication/)
- [docs.healthex.io — FHIR Server](https://docs.healthex.io/fhir-server/)
- [docs.healthex.io — Adding Patients to Projects](https://docs.healthex.io/add-patients-to-projects/) · [Add Patients by Unique Link](https://docs.healthex.io/add-patients-to-projects/add-patients-by-unique-link)
- [docs.healthex.io — Patient Demographics](https://docs.healthex.io/patient-demographics) · [Data Retrieval Status](https://docs.healthex.io/data-retrieval-status)
- [docs.healthex.io — API reference](https://docs.healthex.io/api) · [Usage](https://docs.healthex.io/usage) · [Sample Patients](https://docs.healthex.io/sample-patients/) · [Test Patients](https://docs.healthex.io/test-patients)
- [docs.healthex.io — MCP Server](https://docs.healthex.io/mcp-server/)
- [HealthEx platform launch press release](https://www.globenewswire.com/news-release/2025/08/12/3131938/0/en/HealthEx-Launches-Platform-to-Empower-Patients-with-Real-time-Health-Record-Access-in-Collaboration-with-Industry-Leaders.html)
- [Sequoia — Designated QHINs](https://rce.sequoiaproject.org/designated-qhins/) (HealthEx is **not** on this list)

## How HealthEx differs from MyChart/Epic

| Concern | MyChart / Epic (existing) | HealthEx |
|---|---|---|
| Who owns the user↔hospital linkage | We do, via `mychart_connections(user_uid, organization_alias)` | HealthEx does — invisible to us |
| Auth | SMART-on-FHIR per-patient OAuth + JWT private_key_jwt + Fernet-encrypted refresh tokens | **Org-level API key + secret → 24h JWT bearer**, one credential for all consented patients |
| Per-tenant PEM / JWKS kid | Yes | None |
| Per-user state | 3 encrypted tokens + refresh lifecycle | Just `healthex_patient_id` (UUID) + status |
| Race-safe refresh | `SELECT FOR UPDATE` on connection row | Not needed — JWT is process-cached |
| Onboarding shape | Redirect → Epic UI → callback to `/auth/finish` with auth code → exchange for tokens | API mints Unique Link → user opens in browser → consents on healthex.io; **no callback** — we discover state by polling |
| Knowing when data is ready | Always immediate post-token | **Asynchronous** — poll until patient resolved by externalId, then poll data-retrieval-status |
| Primary fetch | `GET /Patient/{id}/$everything` against org's Epic endpoint | `GET /FHIR/R4/Person/{patientId}/$everything` against `api.healthex.io` |
| FHIR version | DSTU2 / STU3 / R4 (per org) | R4 only |
| Bulk `$export` NDJSON | Yes (`fhir_bulk_extract`) | Not exposed |
| Incremental sync | We compute `_since` from `last_synced_at` | Native `?_since=<ts>` (timestamp-filtered, not guaranteed minimal delta — keep dedup ledger) |
| Consent enforcement | Implied by token possession | HealthEx-side, per-Project; org JWT only sees patients consented to projects we own |
| Push (webhooks) | Not applicable | **None** — pull-only, polling required |

## Auth flow

`POST https://api.healthex.io/v1/auth/token` returns the org JWT. **Live-verified shape**:

- Headers: `Content-Type: application/json`, `Accept: application/json`
- Body: `{"apiKey": "<key>", "apiSecret": "<secret>"}`
- **HTTP 201** (not 200) on success
- Response: `{"token": "<jwt>", "expiration": <absolute_unix_epoch_seconds>}`
- JWT decoded claims include `organizationId`, `permissions` (e.g. `[ORG_ADMIN]`), `type` (e.g. `API_EXTERNAL_RESEARCHER`)

→ **No separate `HEALTHEX_ORG_ID` env var needed** — derive from JWT if/when wanted.

Token caching is in-process with a 60s skew before the server-reported `expiration`. Refresh is gated by an `asyncio.Lock` to avoid bursting `/auth/token` on parallel cache misses.

## URL terminology quirk

HealthEx documentation says **"Project"** everywhere but their REST API uses both `/v1/projects/` and `/v1/studies/` interchangeably:

| Operation | URL |
|---|---|
| getStudyById | `GET /v1/studies/{id}` |
| addPatients (batch, org-push, not our path) | `POST /v1/projects/{id}/patients` |
| getProjectLinkForPatient (the Unique Link) | `POST /v1/projects/{id}/link` |
| getPatientDemographics | `GET /v1/projects/{id}/patients/{patientId}/demographics` |
| has-patient-consented-to-study (the externalId lookup) | `GET /v1/patients/consented/study/{id}/PATIENT_DIRECTED_DATA_EXCHANGE?externalId=…` |
| FHIR $everything | `GET /FHIR/R4/Person/{patientId}/$everything` |

The org-JWT is required for all of these. **There is no FHIR SMART-on-FHIR discovery** (`/FHIR/R4/.well-known/smart-configuration` returns 404 even with valid auth) — the CapabilityStatement security block declares: *"Use HealthEx API keys for authorized access to FHIR APIs"*.

## Data model

- **Project** (aka "study" in URLs) — the unit of purpose ("breast cancer registry", "MM cohort"). Every patient is added to a project; consent is per-project, not per-org.
- **Patient** — gets a HealthEx UUID (`patientId`) plus an optional `externalId` we supply (our `user_uid` slot).
- **Consent** — two types: **Data Authorization** (access via healthcare organizations) and **Patient Directed Data Exchange** (access via public data networks, i.e. TEFCA). Granular scopes by FHIR resource type + sensitivity category. **For consumer-app integration, the relevant consent type is `PATIENT_DIRECTED_DATA_EXCHANGE`.**

## Onboarding: Unique Link (our chosen path)

HealthEx supports three onboarding shapes. Only **Unique Link** is the right fit for a consumer app where users initiate the connection themselves:

| Shape | Use case | Fits us? |
|---|---|---|
| **Generic Link** (one URL per project, no externalId) | Public study recruitment | No — we can't tie a consent back to a user |
| **Unique Link** (per-patient URL with externalId + signature) | Consumer app integration | ✅ **This** |
| **addPatients API** (`POST /v1/projects/{id}/patients`, batch) | Org-initiated outreach (email/SMS via HealthEx) | No — wrong direction; also returns only `{successCount, errorCount, …}`, no `patientId` |

### Mint the link (live-verified)

`POST https://api.healthex.io/v1/projects/{projectId}/link`

- Headers: `Authorization: Bearer <jwt>`, `Content-Type: application/json`
- Body: `{"externalId": "our-user-uid"}`. Omit `externalId` to get a generic link.
- **HTTP 201**, `Content-Type: text/html`, body is the **raw URL as a string** (NOT JSON)
- Returned URL format: `https://app.healthex.io/#/patient-consent/{projectId}/enrollment/link?xid={externalId}.{signature}`

The `xid` carries our externalId concatenated with a server-generated HMAC-style signature. **Cannot be constructed client-side** — docs explicitly say *"links are generated with a cryptographic signature. Do not attempt to construct your own links!"*

Re-issuing a link for the same `externalId` is idempotent on HealthEx's side (mints a fresh signature). We persist the first one and serve it on subsequent `/healthex/connect` calls.

### After the user clicks the link

HealthEx hosts the consent UI. Identity verification uses **CLEAR** (NIST IAL2/AAL2). **No callback to us.** We discover the patient state by polling.

### Externalid → patientId lookup (live-verified)

`GET https://api.healthex.io/v1/patients/consented/study/{projectId}/PATIENT_DIRECTED_DATA_EXCHANGE?externalId={uid}`

- While pending: **HTTP 400** with body `{"message": "Patient not found for provided externalId", ...}`. Our client returns `None` on this exact sentinel.
- Once consented: HTTP 200 with the patient record (response shape **not yet observed end-to-end** — `_extract_patient_id` accepts dict, list-of-dicts, or list-of-strings defensively until we see a real consent).

This is the load-bearing transition: **once this returns a non-null `patientId`, the user has consented** and we can call `$everything`.

## FHIR API surface

- **Base**: `https://api.healthex.io/FHIR/R4/`
- **CapabilityStatement** confirmed: `fhirVersion 4.0.1`, 146 resource types exposed (Patient, Observation, Condition, MedicationRequest, Procedure, DocumentReference, etc.)
- **Primary endpoint**: `GET /Person/{patientId}/$everything` — returns a unified Bundle. Verified via 403 "Not allowed to access patients who have not consented to a study in your organization" on a fake patientId (route exists, gated by org-scoped consent table).
- **Paging**: `_count` + `_offset`. **Streaming responses** for large bundles.
- **Filtering**: `_type=Observation,Condition` to limit resource classes.
- **Delta**: `_since=<timestamp>` — returns resources **updated** (not strictly **new**) since T. Docs recommend recording the timestamp at call-start; no explicit dedup guarantee, so we keep our `pushed_resources` ledger.
- **No `$export`**.

## TEFCA / QHIN topology

HealthEx is **not** a Designated QHIN. They connect through:
- **MedAllies** (Designated QHIN)
- **CommonWell Health Alliance** (Designated QHIN)

Data freshness depends on those QHINs' upstream connectors (and ultimately on each EHR's TEFCA-exposed FHIR endpoint). Coverage claims ("80% of U.S. providers") are inherited from the QHINs, not direct.

## Sample patients + test patients (for non-PHI smoke testing)

- **Sample Patients** (125 Synthea-generated bundles, no consent flow needed) — access gated by emailing `partnersupport@healthex.io`. Best path for fast `$everything` smoke testing without real consent.
- **Test Patients** — `POST /v1/organizations/{orgId}/test-patients` returns auto-generated email + password. **Requires the org to have a "domain configured" first** (currently blocks us with HTTP 400 `"Organization does not have a domain configured"` — needs HealthEx admin setup).

## MCP server (separate surface — not our integration target)

HealthEx **hosts** an MCP server at `/mcp` (JSON-RPC 2.0) that AI agents authenticate against with **per-patient OAuth 2.0 + PKCE**. Designed for chatbots (Claude, ChatGPT) to query a patient's record on demand with natural-language ranking. Not the right fit for batch OMOP ingest — for our pipeline, use the FHIR server with the org JWT.

## Code layout (fhir-importers)

| File | Role |
|---|---|
| `app/config.py` | `HEALTHEX_API_KEY` / `HEALTHEX_API_SECRET` / `HEALTHEX_PROJECT_ID` / `HEALTHEX_BASE_URL` env vars |
| `app/healthex_client.py` | `HealthExClient` + `BaseHealthExClient`: token cache, `get_unique_link`, `find_patient_id_by_external_id`, `get_data_retrieval_status` |
| `app/healthex_links.py` | `HealthExLinksRepository`: upsert, get, list, delete, update_status |
| `app/healthex_routers.py` | `POST /healthex/connect`, `GET /healthex/connections`, `DELETE /healthex/connections/{project_id}`, `GET /healthex/connections/{project_id}/status` |
| `app/models.py::HealthExLink` | DB row: `(user_uid, project_id)` unique + `external_id`, `healthex_patient_id`, status, `onboarding_url`, timestamps |
| `app/schemas.py` | `HealthExLinkResponse`, `HealthExStatusResponse` |
| `alembic/versions/0004_healthex_patient_links.py` | Schema migration |
| `test_healthex_flow.py` | Manual e2e smoke harness — mints link → `breakpoint()` → polls patientId → polls status → GETs `$everything` |

State machine for `healthex_patient_links.status`:
```
PENDING_CONSENT → RETRIEVAL_IN_PROGRESS → COMPLETE
                                       └→ ERROR
                       (any state)     → REVOKED
```

## What's still needed (healthkey-etl side, not yet built)

- **Token provider** mirroring `app/healthex_client.py::HealthExClient` (same auth flow, async httpx).
- **Status-polling DAG** `fhir_healthex_poll_status` — periodic scan over `healthex_patient_links` rows in `PENDING_CONSENT` / `RETRIEVAL_IN_PROGRESS`, calls the same `find_patient_id_by_external_id` + `data-retrieval-status` endpoints, writes the resolved `healthex_patient_id` + status back via shared-DB writes (or via a new fhir-importers endpoint). Fires the extract DAG on transition to `COMPLETE`. This replaces the role MyChart's `/auth/finish` callback played.
- **Extract DAG** `fhir_extract_healthex(user_uid, healthex_project_id, healthex_patient_id)` — get JWT → `GET $everything?_since=…` → hand to existing `ingest_artifact`. ~no logic.
- **Reuses untouched**: FHIR R4 parser (`services/fhir_parsing/`), `OmopWriter`, `pushed_resources` idempotency ledger, ctomop HTTP client.

## Known unknowns / open questions

These remain unresolved by public docs + API probes; flagged so future-me doesn't re-discover the hard way:

1. **`get_data_retrieval_status` URL is unverified.** `GET /v1/patients/data-retrieval/status` (the form the docs show) returns **HTTP 403 "Forbidden resource"** with our org-JWT (`API_EXTERNAL_RESEARCHER` role). Could be a role/scope issue, could be the wrong URL. The code path is left in but soft-fails through to the `$everything` call. Will fix when we observe behavior with a real consenting patient.
2. **Response shape of `find_patient_id_by_external_id` (200 case)** — only the 400 "pending" case is observed. `_extract_patient_id` is defensive (accepts dict, list-of-dicts, list-of-strings) until we see a real consent.
3. **Pricing model** — per-call / per-patient-per-month / tiered. Affects polling cadence. **User has said this is not our concern; defer to them.**
4. **Rate limits + burst caps** — not documented. Affects polling design.
5. **`_since` exact semantics** — docs say "updated since T" without specifying whether trivial server-side touches (e.g. re-indexing) bump the timestamp. Empirical test required; our ledger covers us either way.
6. **`/v1/studies/{id}` returns HTTP 200 with empty body** for our project. May be authorization scoped — docs say *"The study must have been added by the caller's organization."* but the project ID we have IS our org's. Not blocking — we don't need study metadata for the flow.

## Coverage caveat

HealthEx claims aggregation from "over 80% of U.S. care providers". This is **marketing**; actual coverage is inherited from MedAllies + CommonWell. Verify against our target hospitals before treating HealthEx as a replacement for direct Epic SMART integration. The two paths likely **coexist** — HealthEx for breadth, direct Epic for specific institutional partnerships and richer scopes.
