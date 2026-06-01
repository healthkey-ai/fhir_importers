# Integration: MyChart/Epic connector ↔ ctomop ↔ host PHR

**Status:** Implemented & verified end-to-end against the Epic sandbox (2026-06-01).

This document describes **how the integration actually works now**. Where the
build diverged from the original integration plan, the difference — and whether it
needs follow-up — is listed in the final section,
[§11 Deviations from the original plan](#11-deviations-from-the-original-plan).

> **Host-agnostic by design.** `ht-phr` is the *reference* host, but it is **just a
> host**. The connector (`fhir_importers`) and the clinical store (`ctomop`) know
> nothing about ht-phr specifically. Any SPA that (a) embeds the connector's
> Module-Federation remote, (b) forwards a verifiable OIDC/Firebase JWT, and (c)
> hosts the Epic callback route can integrate. Throughout this doc, **“Host”**
> means *any* such host; ht-phr is named only as the concrete example.

---

## 1. Components

| Component | Stack | Role |
|---|---|---|
| **Host SPA** (e.g. ht-phr) | React + Vite, Module-Federation **host**, an OIDC IdP (Firebase) | Embeds the connector UI, forwards the user's JWT, hosts the Epic callback route, reads & renders clinical data from ctomop. |
| **`fhir_importers`** (the **Connector**) | Django + DRF, PostgreSQL, MF **remote** | Owns *all* Epic/MyChart auth & communication. Persists Epic tokens (encrypted), fetches FHIR, maps to ctomop, posts the result. Serves its own React remote. |
| **`ctomop`** (the **Clinical store**) | Django + DRF, PostgreSQL (OMOP CDM) | Source of truth for `person_id`. Resolves identity → `Person`, ingests the mapped data, returns record totals. |
| **Epic / MyChart** | SMART-on-FHIR (R4) | The EHR. Authorizes via OAuth2 (PKCE + private-key JWT) and serves FHIR resources. |

All three platform services share one **OIDC `(issuer, sub)` Identity** model — a
patient is the same `Identity` everywhere, and `ctomop` is the only service that
maps that Identity to a `Person`.

---

## 2. Architecture (as built)

```
                 ┌────────────────────────────────────────────────────────────┐
                 │                      HOST SPA  (e.g. ht-phr)                 │
   Patient ──────►  • MF host: consumes  mychart_remote/{ConnectMyChart,        │
   (OIDC/Firebase)  │                     MyChartCallback}                       │
                 │  • Route: /connect/records      (Connect + status UI)        │
                 │  • Route: /connect/mychart/callback  (Epic redirect target)  │
                 │  • axios → Connector  (Authorization: Bearer <host JWT>)     │
                 │  • axios → ctomop      (Authorization: Bearer <host JWT>)     │
                 └─────┬──────────────────────────────────────────┬────────────┘
                       │ (A) connect / sync / poll                 │ (F) read clinical data
                       │     Bearer: host JWT (Firebase)           │     Bearer: host JWT
                       ▼                                           ▼
   ┌───────────────────────────────────────────────┐     ┌──────────────────────────────┐
   │     fhir_importers  —  CONNECTOR (Django)       │     │           ctomop              │
   │                                                 │     │  PartnerAuthentication →      │
   │  PartnerAuthentication (Firebase) → Identity    │     │    Identity(iss,sub)          │
   │  Connection(identity FK, Epic tokens=Fernet,    │     │    → resolve_or_create_person │
   │             org_alias, epic_patient_id)         │     │    → Person                   │
   │  SyncJob(connection FK, status, counts, totals) │     │                               │
   │  EpicAuthState(PKCE state, DB-backed)           │     │  POST /api/fhir/sync/         │
   │                                                 │ (E) │   body:{actor_iss,actor_sub,  │
   │  Epic OAuth: PKCE + private-key-JWT (RS256)     │────►│         bundle}  (no person_id)│
   │  JWKS served at /epic/.well-known/jwks.json     │     │   auth: CTOMOP_SERVICE_TOKEN  │
   │  EpicFhirClient: per-resource fetch + paginate  │     │         (service-token)       │
   │  Map Epic FHIR(R4) → OMOP bundle, 400-row chunks│     │  → OMOP rows + ProvenanceRecord│
   │  Serves mychart_remote via WhiteNoise (/static) │     │    (source=EHR_SYNC)          │
   └──────┬──────────────────────────────────────────┘     └──────────────────────────────┘
          │ (B) authorize  (C) token  (D) FHIR read
          ▼
   ┌────────────────────┐
   │   Epic / MyChart   │   (authorization + token + FHIR R4 endpoints)
   └────────────────────┘
```

`(A)…(F)` map to the end-to-end flow in §3.

---

## 3. End-to-end flow

**Connect (OAuth):**

1. **(A)** Patient opens the Host's connect page; the Host renders
   `mychart_remote/ConnectMyChart`, passing an **authenticated axios instance**
   (base URL = the Connector, `Authorization: Bearer <host JWT>`).
2. The remote calls `GET /epic/organizations` (Connector verifies the JWT →
   `Identity(iss, sub)`), the patient picks a hospital, and the remote calls
   `POST /epic/auth/start`. The Connector builds the SMART authorize URL
   (PKCE `code_challenge`; stores PKCE state in **`EpicAuthState`**) and returns it.
3. **(B)** Browser redirects to **Epic**; patient logs in and consents.
4. Epic redirects back to the **Host's** callback route
   (`/connect/mychart/callback`); `mychart_remote/MyChartCallback` calls
   `POST /epic/auth/finish` with the `code` + `state`.
5. **(C)** Connector exchanges the code (signing a **private-key-JWT** client
   assertion, verified by Epic against the Connector's hosted JWKS) → Epic access
   + refresh tokens. It **persists a `Connection`** (tokens **Fernet-encrypted**,
   `epic_patient_id`, `org_alias`, FK → caller's `Identity`) and kicks off a
   `SyncJob`. **Tokens never reach the browser.**

**Sync (ingest):**

6. **(D)** The sync job uses the Connection's token (auto-refreshing on expiry via
   the `offline_access` refresh token) and `EpicFhirClient` to pull FHIR R4
   **per resource type** — Epic has no `Patient/$everything`, so:
   `Patient` read · `Observation?category=laboratory` · `?category=vital-signs` ·
   `Condition` · `MedicationRequest` (paginated).
7. The Connector maps Epic FHIR → ctomop's bundle shape and **(E)** posts it to
   **`POST /api/fhir/sync/`** in **≤400-entry chunks**, with `actor_iss`/`actor_sub`
   from the Connection's Identity and **no `person_id`** — authenticated by
   `CTOMOP_SERVICE_TOKEN` (a service token).
8. **ctomop** resolves the patient from `(actor_iss, actor_sub)` →
   `resolve_or_create_person` → `Person`, writes OMOP rows with
   `ProvenanceRecord(source='EHR_SYNC')`, and returns per-person **record totals**.
   The Connector accumulates per-category counts onto the `SyncJob`.

**Display:**

9. The Host polls `GET /epic/sync/{job_id}` for live progress; on completion it
   **(F)** refetches from ctomop (`Authorization: Bearer <host JWT>`; ctomop
   resolves the same Identity → same `Person`) and renders demographics, labs,
   conditions, and medications.

**Re-sync / disconnect:** `POST /epic/connections/{id}/sync` re-runs;
`DELETE /epic/connections/{id}` disconnects. All `/epic/*` calls are scoped to the
caller's Identity, so a patient only ever sees their own connections.

---

## 4. The integration contract (what a Host must provide)

This is the host-agnostic surface. To integrate, a Host provides exactly four things:

1. **Consume the remote.** Add `mychart_remote` to the host's Module-Federation
   config and import the exposed components:
   - `mychart_remote/ConnectMyChart` — the connect widget.
   - `mychart_remote/MyChartCallback` — the callback handler.
   - `mychart_remote/types` — shared TS types.
   Shared singletons required by the remote: `react`, `react-dom`,
   `react/jsx-runtime`, `axios`.
2. **Forward a verifiable JWT.** Pass the remote an axios instance whose
   `Authorization: Bearer` is the user's OIDC token. The Connector's
   `PartnerAuthentication` must be able to verify it — out of the box that's a
   **Firebase** ID token (`FIREBASE_PROJECT_ID`); other OIDC providers plug in via
   the same `TokenProvider` registry. The **same** token also authenticates the
   Host's reads against ctomop, so both services resolve the **same** `Identity`.
3. **Host the callback route.** Expose a route at the Epic-registered
   `redirect_uri` that renders `MyChartCallback`. The redirect URI is configured
   **per host/environment** (Connector env `EPIC_*_REDIRECT_URI`, and registered in
   the Epic app).
4. **Read from ctomop** for display (the Connector does not serve clinical data).

A Host needs **no backend changes** for identity: the JWT is forwarded and ctomop
resolves the `Person`. Anything like a host-cached `phr_person_id` is an optional
display convenience, never load-bearing.

> Swapping ht-phr for another host = point these four things at the new host's
> origin and register that host's callback URI with Epic. The Connector and ctomop
> are unchanged.

---

## 5. Identity & trust

- **One Identity everywhere.** Each service stores a thin `Identity(issuer, sub)`;
  profile fields come from JWT claims at request time, never persisted for external
  identities. The Connector and ctomop copy the same Identity stack (`Identity` +
  `IdentityManager`, `providers/{base,firebase,registry}`, `PartnerAuthentication`,
  `ServiceTokenAuthentication`) from the shared pattern.
- **ctomop owns person linkage.** The Connector **never stores `person_id`**.
  ctomop maps `(iss, sub) → PatientUser → Person`, auto-provisioning on first
  contact. Because the Host hits ctomop (read) before any Epic sync, the `Person`
  already exists; the sync resolves the same `(iss, sub)` → no duplicate.
- **Two trust edges:**
  - *Host → Connector* and *Host → ctomop*: the **patient's** OIDC/Firebase JWT
    (PartnerAuthentication).
  - *Connector → ctomop*: a **service token** (`CTOMOP_SERVICE_TOKEN`), with the
    patient's identity carried in the request **body** (`actor_iss`/`actor_sub`).
    ctomop's `ScopedTokenPermission` grants writes to service-token / staff /
    superuser callers only — so the Connector (service token) may POST `/sync/`,
    while a raw patient token cannot.
- **Epic ↔ Connector:** SMART-on-FHIR with **PKCE** + **private-key-JWT** client
  authentication (RS256). Epic verifies the Connector's assertions against the
  **JWKS the Connector hosts** at `/epic/.well-known/jwks.json`, so key rotation is
  a deploy, not a re-registration.

---

## 6. Data mapping (Epic FHIR R4 → OMOP CDM)

| Epic FHIR | OMOP | Notes |
|---|---|---|
| `Patient` | `Person` (+ `PatientInfo`) | Demographics fill empty fields only; never clobbers. |
| `Observation` (LOINC, `laboratory`/`vital-signs`) | `Measurement` | Concept matched by LOINC; unmatched → HK placeholder concept. |
| `Condition` | `ConditionOccurrence` | `onsetDateTime`/`onsetPeriod` → start date. |
| `MedicationRequest` / `MedicationStatement` | `DrugExposure` | Epic R4 exposes meds primarily as `MedicationRequest` (`authoredOn`). |

**First-cut scope = demographics + labs + conditions + medications.** Oncology
enrichment (ECOG, stage, ER/PR/HER2 biomarkers, therapy-line episodes) is
**deferred → issue #10**; until it lands, oncology-specific `PatientInfo` fields
stay empty for Epic-sourced patients.

---

## 7. Connector API surface

All under `/epic/` unless noted; `/epic/*` requires the patient JWT and is
Identity-scoped. `POST /api/fhir/sync/` is on **ctomop**.

| Method & path | Purpose |
|---|---|
| `GET /epic/organizations` | List connectable hospitals (excludes already-connected). |
| `POST /epic/auth/start` | Begin SMART auth → returns Epic authorize URL. |
| `POST /epic/auth/finish` | Exchange code → persist `Connection`, start sync. |
| `GET /epic/connections` | The caller's connections. |
| `DELETE /epic/connections/{id}` | Disconnect (remove tokens). |
| `POST /epic/connections/{id}/sync` | Re-sync an existing connection. |
| `GET /epic/sync/{job_id}` | Poll a `SyncJob` (status, counts, totals). |
| `GET /epic/.well-known/jwks.json` | Public signing keys for Epic (private-key-JWT). |
| `GET /health/` | Liveness. |
| `POST /api/fhir/sync/` *(ctomop)* | Identity-resolved OMOP ingest (service-token). |

**MF remote `mychart_remote`** exposes `./ConnectMyChart`, `./MyChartCallback`,
`./types` (served by the Connector via WhiteNoise at `/static/remoteEntry.js`).

---

## 8. Deployment topology (GCP staging)

All services share one GCP project (`ht-phr`) and one Cloud SQL Postgres instance
(`ht-phr-staging-db`), **one database per service**.

```
   GitHub (per repo)
     │  push → dev → GitHub Actions (Workload Identity Federation, no keys)
     ▼
   Artifact Registry  ──image──►  Cloud Run service (per service)
                                    fhir-importers-staging  ht-phr / ctomop / hk-labs
                                       │  Cloud SQL socket        │
                                       ▼                          ▼
                                  Cloud SQL  (db: fhir_importers, ctomop, …)
                                  Secret Manager  (django key, database-url,
                                     token-encryption-key, epic key, service token)
```

Connector specifics:
- **Image** is two-stage: builds the MF remote, then a Django runtime that **serves
  the remote** via WhiteNoise. The Host loads it from
  `https://<connector>/static/remoteEntry.js`.
- **`TASK_BACKEND=eager`** — sync runs **inline** in the request (the Cloud Run
  module has no VPC connector / Memorystore, so there is no Celery worker). Locally,
  Celery + Redis is available.
- **PKCE state is DB-backed** (`EpicAuthState`) so it survives across stateless
  Cloud Run instances (`min_instances=0`). Redis remains available behind
  `EPIC_STATE_BACKEND=redis`.
- **Epic key & secrets** are injected from Secret Manager (`EPIC_STAGING_PRIVATE_KEY`
  inline PEM; `TOKEN_ENCRYPTION_KEY` Fernet; `CTOMOP_SERVICE_TOKEN`; `DATABASE_URL`).
- **Host wiring** (per host, build-time): `VITE_MYCHART_REMOTE_URL=<connector>/static`
  and `VITE_FHIR_IMPORTER_URL=<connector>` (API base).

---

## 9. Status vs plan

**All six planned phases are implemented and the end-to-end demo works** (verified
against the Epic sandbox: 1612 resources fetched → 746 created in ~11 s).

| Phase | Plan | Status |
|---|---|---|
| 0 — Django port + Identity | ✅ | Done — connector is a platform Django service with the shared Identity stack. |
| 1 — Embed remote in host | ✅ | Done — `mychart_remote` + connect page + callback route. |
| 2 — Persistence + ctomop sync | ✅ | Done — `Connection`/`SyncJob`, encrypted tokens, ctomop `POST /api/fhir/sync/`. |
| 3 — Epic FHIR fetch | ✅ | Done — **per-resource** fetch + pagination + token refresh. |
| 4 — Map + orchestrate + display | ✅ | Done — first-cut mapping, status polling, host renders. |
| 5 — Hardening | ◑ | Token encryption ✅, staging deploy ✅, idempotent re-sync (ctomop dedup) ✅. Full PHI security review still open. |

All deviations from the original plan are catalogued in
[§11](#11-deviations-from-the-original-plan), with whether each needs follow-up.

---

## 10. Definition of done — met

A patient logs into a Host, clicks *Connect to <hospital>*, completes Epic SMART
login, and within one sync sees their demographics, labs, conditions, and
medications — sourced from Epic, written to ctomop's OMOP tables with `EHR_SYNC`
provenance, linked to a single `Person` resolved from the shared `(issuer, sub)`
identity, with Epic tokens persisted (encrypted) only in the connector. The
connector runs as a platform Django service in both standalone and integrated
modes, and is embeddable by **any** conforming host — ht-phr is merely the first.

---

## 11. Deviations from the original plan

Every place the build differs from the original integration plan, and whether it
needs follow-up. **Accepted** = a deliberate as-built design, no action required.
**Action needed** = open work.

### Accepted design changes (no action needed)

| # | Deviation | Why it changed |
|---|---|---|
| 1 | **Per-resource FHIR fetch**, not `Patient/$everything` | Epic doesn't implement `$everything`; the connector pulls `Patient` + `Observation?category=laboratory`/`vital-signs` + `Condition` + `MedicationRequest`, paginated. |
| 2 | **PKCE state is DB-backed** (`EpicAuthState` + `DbStateStore`), not Redis | Cloud Run is stateless (`min_instances=0`, no shared cache); a DB store survives across instances. Redis remains opt-in via `EPIC_STATE_BACKEND=redis`. |
| 3 | **Inline Epic signing key** (`EPIC_*_PRIVATE_KEY` PEM from Secret Manager), not a file path | Secret Manager injects secrets as env vars on Cloud Run; the connector resolves inline-or-file. |
| 4 | **Connector serves its own MF remote** (two-stage Dockerfile + WhiteNoise at `/static`) | A production host must load `remoteEntry.js` cross-origin from the connector. |
| 5 | **Chunked ingest (≤400 rows/POST)** + per-person **record totals** returned | Keeps each `/api/fhir/sync/` call under ctomop's per-request entry limit; totals drive the host UI. |

### Resolved during integration

| Item | Resolution |
|---|---|
| **OMOP PK sequence collision** — legacy `MAX(id)+1` writers stranded Postgres sequences, so the sequence-based sync hit `duplicate key` 500s | Fixed in ctomop: `next_pk`/`next_pk_batch` self-heal the sequence to `≥ MAX(id)` before allocating. **Merged (PR #108) and live on ctomop-staging** (serving revision runs `pk.py` with `_reseed_to_max`). No more manual reseeds needed. |

### Action needed

| # | Item | What needs doing | Owner / tracking |
|---|---|---|---|
| 6 | **Legacy `MAX(id)+1` writers remain** | #108 makes the *sync* path self-healing, but the legacy writers (`patient_portal/api/views.py`, `lot_inference_service`, `omop_write_service`) still assign explicit PKs without advancing the sequence — a latent footgun. Durable cure: migrate them to `next_pk`. | ctomop follow-up |
| 7 | **Cloud sync runs inline (`TASK_BACKEND=eager`)**, not Celery | Acceptable now (sync ~11 s), but there's no async/retry and it holds the request open. If bundles grow or Epic is slow, add an async backend (Cloud Tasks HTTP dispatch, à la hk-labs — no VPC/Redis needed). | Revisit at scale |
| 8 | **Re-sync is not self-reconciling** | The connector doesn't remove its prior `EHR_SYNC` rows before a re-sync; it relies on ctomop's content-dedup, which doesn't cover everything (clean re-tests currently clear rows manually). Implement reconcile-on-resync (or confirm ctomop dedup is sufficient). | Phase 5 |
| 9 | **Oncology enrichment deferred** | ECOG, stage, ER/PR/HER2 biomarkers, therapy-line episodes aren't mapped, so those `PatientInfo` fields stay empty for Epic-sourced patients. | **issue #10** |
| 10 | **PHI security review + hardening** | Full PHI/security review, retry/backoff, error surfacing — the Phase 5 tail. | Phase 5 |
