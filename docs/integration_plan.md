# Integration Plan: fhir_importers ↔ ctomop ↔ ht-phr

**Status:** Proposed
**Date:** 2026-05-31
**Owner:** vtrv101

## 1. Goal

Deliver an end-to-end "Connect MyChart" pipeline for the patient-facing PHR:

> A patient in **ht-phr** clicks *Connect MyChart*, authenticates with their hospital's Epic
> via SMART-on-FHIR, and their clinical data is pulled from Epic and stored in **ctomop**
> (OMOP CDM), then displayed back in the PHR.

Agreed design decisions:

- **`fhir_importers`** is promoted from an OAuth broker to a **full HealthKey FHIR connector**:
  it owns *all* authentication and communication with MyChart/Epic, persists Epic tokens, fetches
  FHIR resources, and **uses ctomop's API to store** the imported data.
- **`fhir_importers` is ported to Django/DRF** so it joins the HealthKey platform exactly like
  `hk-labs` and `ctomop`, adopting the shared OIDC Identity architecture
  (see `ctomop/docs/identity-architecture.md`) by copying the Identity app + providers verbatim
  (and, when available, the `healthkey-identity` pip package).
- **`ctomop`** remains the clinical store / ingest target; it resolves patient identity itself and
  is the single source of truth for `person_id`.
- **`ht-phr`** is the Module-Federation host: it embeds the connector UI, forwards its Firebase JWT,
  triggers connect + sync, and renders the resulting data (already read from ctomop).

## 2. Current State (verified against code)

### Identity architecture — already implemented in ctomop (the pattern to copy)
- `patient_portal.Identity` is `AUTH_USER_MODEL` (`ctomop/settings.py:148`); minimal `(issuer, sub)`
  anchor with `IdentityManager.get_or_create_from_claims()` (`patient_portal/models.py:48`).
- `PartnerAuthentication` DRF backend (`patient_portal/api/authentication.py`) iterates
  `PARTNER_AUTH_PROVIDERS`, routes by `provider.can_handle()` on the unverified payload, calls
  `verify()`, then `get_or_create_identity()` + `_ensure_person()`; caches verified tokens 60s.
- Pluggable providers under `patient_portal/api/providers/` — `base.py` (`TokenProvider` ABC,
  `TokenClaims`, `decode_jwt_unverified`), `firebase.py`, `registry.py`.
- `_ensure_person(identity, claims)` → `patient_portal.services.resolve_or_create_person()`
  auto-provisions `Person` + `PatientInfo` + `PatientUser` on first login.
- `PatientUser(identity → Identity, person → Person)` is the identity↔Person link.
- `ServiceTokenAuthentication` (pre-shared bearer) exists for service-to-service calls.
- **Canonical cross-service ingest pattern:** `POST /api/lab-results/sync/`
  (`patient_portal/api/lab_results/sync.py`, `SyncView`, `permission_classes=[ScopedTokenPermission]`).
  Accepts `person_id?`, `actor_iss?`, `actor_sub?`, payload; resolves Person from the actor identity
  (`resolve_or_create_person` / `_resolve_person_from_identity`), enforces `can_access_patient()` for
  on-behalf-of writes. **hk-labs never stores a person_id — ctomop resolves it.**
- Two modes: **standalone** (`PARTNER_AUTH_PROVIDERS=[]`, local `iss="urn:local"` users) and
  **integrated** (Firebase provider configured, host forwards JWT). Switching is settings-only.

### ctomop — OMOP CDM clinical store (Django 4.2 + DRF, PostgreSQL)
- FHIR ingest today: `POST /api/patient-info/upload_fhir/` (`patient_portal/api/views.py:422`),
  multipart bundle, OAuth2 `client_credentials` + `patient/*.write`, **Person keyed by demographic
  upsert** — predates the identity-resolution sync pattern.
- Maps Patient→Person, Condition→ConditionOccurrence, Observation(LOINC)→Measurement,
  MedicationStatement→DrugExposure/Episode; rebuilds `PatientInfo`; writes `ProvenanceRecord`.
- Uses ctomop-specific FHIR extensions (`http://ctomop.io/fhir/StructureDefinition/*`).

### fhir_importers — Epic OAuth broker (FastAPI, no DB) — to be ported
- `GET /epic/organizations`, `POST /epic/auth/start`, `POST /epic/auth/finish`, `GET /health`.
- `EpicAuthService` + `EpicClient`: PKCE + private-key JWT (RS256) SMART flow; `RedisStateStore`
  holds ephemeral PKCE state (TTL 600s). **No DB, no token persistence, no FHIR fetch, no ctomop call.**
- Frontend MF **remote** `mychart_remote` exposing `./ConnectMyChart`, `./MyChartCallback`, `./types`;
  host injects an authenticated axios instance; tokens currently handed to host via `onSuccess`.

### ht-phr — patient PHR host (Django 5 + DRF, React 19 + Vite, Firebase, Celery)
- MF **host** (`ht_phr_host`) consuming `labs_remote`, `labs_results_remote`.
- Auth: Firebase ID token; `User.phr_person_id` exists but, under the shared identity model, becomes
  an **optional cache** — ctomop resolves identity→Person on every call, so it is not load-bearing.
- Hooks `usePhrApi()`, `useLabsApi()`, `useCtomopApi()` build axios with a Firebase-token interceptor.

## 3. Target Architecture

```
                       ┌─────────────────────────────────────────────┐
   Patient ──Firebase──►                  ht-phr (host SPA)            │
                       │  • embeds mychart_remote/ConnectMyChart       │
                       │  • Connect page + Epic callback route         │
                       │  • useMyChartApi() → fhir_importers (fwd JWT) │
                       │  • useCtomopApi()  → ctomop (read/display)    │
                       └───────┬───────────────────────────┬──────────┘
                               │ (1) start/finish/sync      │ (6) read clinical data
                               │     Bearer: Firebase JWT    │     Bearer: Firebase JWT
                               ▼                            ▼
        ┌──────────────────────────────────────┐   ┌────────────────────────────┐
        │   fhir_importers (Django CONNECTOR)    │   │           ctomop            │
        │  • Identity (iss,sub) + PartnerAuth     │   │  PartnerAuth → Identity     │
        │    (copied providers: Firebase, local) │   │  → _ensure_person → Person  │
        │  • Connection, SyncJob  (FK → Identity)│   │                             │
        │    Epic tokens encrypted; NO person_id │   │  NEW POST /api/fhir/sync/   │
        │  • Epic OAuth (PKCE + private-key JWT)  │──►│  body: actor_iss/actor_sub, │
        │  • EpicFhirClient (fetch + paginate)   │(5)│        bundle [+ person_id]  │
        │  • Map Epic FHIR → ctomop bundle       │   │  auth: service token /      │
        │  • CtomopSyncClient (Celery task)      │   │        client_credentials   │
        └───────┬────────────────────────────────┘   │  → OMOP tables + PatientInfo│
                │ (2)(3)(4) authorize/token/$everything│   └────────────────────────────┘
                ▼
        ┌────────────────────┐
        │   Epic / MyChart   │
        └────────────────────┘
```

**End-to-end flow:**
1. Patient clicks *Connect MyChart* (embedded `mychart_remote`); ht-phr passes `useMyChartApi()`
   (base URL `VITE_FHIR_IMPORTER_URL`, **forwarding the Firebase JWT**).
2. `fhir_importers` `PartnerAuthentication` verifies the JWT → resolves local `Identity(iss, sub)`.
   `ConnectMyChart` → `POST /epic/auth/start` → redirect to Epic.
3. Epic redirects to ht-phr's callback route → `MyChartCallback` → `POST /epic/auth/finish`.
4. `fhir_importers` exchanges code → Epic tokens and **persists a `Connection`** (encrypted Epic
   access/refresh tokens, `epic_patient_id`, `org_alias`, FK → the caller's `Identity`) instead of
   returning tokens to the browser. It enqueues a Celery **`SyncJob`**.
5. Sync task: `EpicFhirClient` pulls FHIR (`Patient/$everything` / per-resource, paginated, refresh
   on expiry) → maps to ctomop's bundle shape → `CtomopSyncClient` `POST`s to **`/api/fhir/sync/`**
   with `actor_iss`/`actor_sub` taken from the Connection's Identity. **No person_id is sent or
   stored** — ctomop resolves the patient via `_ensure_person`/`resolve_or_create_person`.
6. ctomop writes OMOP rows (provenance `EHR_SYNC`) and rebuilds `PatientInfo`. ht-phr polls
   `GET /sync/{job_id}`; on completion it refetches from ctomop via `useCtomopApi()` and renders.

## 4. Identity & Trust (per `ctomop/docs/identity-architecture.md`)

- **Shared anchor:** every service stores a thin `Identity(issuer, sub)`; user profile fields come
  from JWT claims at request time, never persisted for external identities.
- **fhir_importers adopts the pattern by copying** the `Identity` model + `IdentityManager`,
  `providers/{base,firebase,registry}.py`, `PartnerAuthentication`, and `ServiceTokenAuthentication`
  from ctomop/hk-labs (later: replace with the `healthkey-identity` pip package). It sets
  `AUTH_USER_MODEL = "<app>.Identity"` and `PARTNER_AUTH_PROVIDERS = [FirebaseTokenProvider]`
  (integrated) or `[]` (standalone).
- **Connector data links to Identity** like hk-labs' `UploadJob.user → Identity`:
  `Connection.identity → Identity`, `SyncJob.connection → Connection`.
- **Cross-service write** uses the self-service pattern: fhir_importers sends
  `{actor_iss, actor_sub, bundle}`; ctomop does `Identity.get_or_create(iss, sub)` →
  `PatientUser` → `Person`, auto-provisioning if new. On-behalf-of (navigator) additionally sends
  `person_id` and ctomop enforces `can_access_patient()`.
- **fhir_importers never stores `person_id`** — ctomop is the source of truth for person linkage.
  ht-phr's `User.phr_person_id` is therefore optional/cache-only and not required for this flow.
- **Service-to-service transport auth** for `/api/fhir/sync/`: **mirror hk-labs exactly** — copy
  `hk-labs backend/apps/labs/ctomop_client.py`. Identity travels in the body (`actor_iss`/`actor_sub`);
  transport is authenticated with `CTOMOP_SERVICE_TOKEN` — an OAuth2 bearer scoped `patient/*.write`
  (so it satisfies the client_credentials intent while staying byte-for-byte consistent with the proven
  hk-labs client). The user's Firebase token may be forwarded instead when present. Config keys reused
  verbatim: `CTOMOP_BASE_URL` / `CTOMOP_SYNC_URL`, `CTOMOP_SERVICE_TOKEN`.
- **Both modes supported:** standalone (local `urn:local` identities, own login, optionally no
  ctomop) and integrated (Firebase JWT forwarded by ht-phr) — a settings change, not code.

## 5. Work Breakdown by Repo

### 5.1 fhir_importers — port to Django + become a stateful connector (largest effort)
- **Django/DRF scaffold:** new Django project; port Epic OAuth modules (`jwt_utils`, `client`,
  `service`, `organizations`, `schemas`) into a Django app; keep Redis for ephemeral PKCE state;
  endpoints become DRF views (`/epic/organizations`, `/epic/auth/start`, `/epic/auth/finish`).
- **Identity adoption (copy from ctomop):** `Identity` + `IdentityManager`, `providers/`,
  `PartnerAuthentication`, `ServiceTokenAuthentication`; `AUTH_USER_MODEL`, `PARTNER_AUTH_PROVIDERS`.
- **Persistence (PostgreSQL):**
  - `Connection`: `identity` (FK), `org_alias`, `epic_patient_id`, `access_token`, `refresh_token`,
    `token_expires_at`, `scope`, timestamps. **Tokens encrypted at rest** (Fernet/KMS key via secret).
    **No `person_id`.**
  - `SyncJob`: `connection` (FK), `status` (`queued|running|succeeded|failed`), counts (resources
    fetched, created/updated downstream), `error`, started/finished.
- **`EpicFhirClient` (new):** use the Connection's token to call Epic FHIR (`Patient/$everything` or
  per-resource); pagination; auto-refresh via `refresh_token` (scope already has `offline_access`).
- **FHIR → ctomop mapping (new):** normalize raw Epic FHIR into ctomop's expected bundle shape.
  **First-cut scope (decided):** demographics + labs (LOINC Observations) + conditions + medications
  only — Patient→Person, Observation→Measurement, Condition→ConditionOccurrence,
  MedicationStatement→DrugExposure. Oncology-specific enrichment (ECOG, stage, ER/PR/HER2 biomarkers,
  therapy-line episodes) is **explicitly deferred** and tracked in **issue #10**.
- **`CtomopSyncClient` (new):** **copy hk-labs' `ctomop_client.py`**; `POST` the bundle to
  `CTOMOP_SYNC_URL` (→ `/api/fhir/sync/`) with `actor_iss`/`actor_sub` and provenance `EHR_SYNC`,
  authenticated by `CTOMOP_SERVICE_TOKEN`; record results on `SyncJob`.
- **Orchestration (Celery, Django-native):** `/epic/auth/finish` persists `Connection` + enqueues a
  `SyncJob`. New endpoints: `GET /connections`, `POST /connections/{id}/sync` (re-sync),
  `GET /sync/{job_id}` (poll). All protected by `PartnerAuthentication` so a caller only sees their
  own Identity's connections.
- **Config:** `CTOMOP_BASE_URL`/`CTOMOP_SYNC_URL` + `CTOMOP_SERVICE_TOKEN`, Firebase project id,
  token-encryption key, `DATABASE_URL`, `PARTNER_AUTH_PROVIDERS`; CORS allows ht-phr origins.
- **Deploy target (decided):** **GCP Cloud Run** matching ht-phr/hk-labs — Cloud SQL (Postgres),
  Secret Manager, GitHub Actions OIDC deploy; reuse ht-phr's deploy pattern.
- **Frontend remote:** keep `ConnectMyChart`/`MyChartCallback`; on `onSuccess`, poll
  `GET /sync/{job_id}` and show progress; optionally expose `MyChartConnections`. Tokens never
  surface to the host.

### 5.2 ctomop — small, additive
- **`POST /api/fhir/sync/` (new, decided):** mirror `lab_results/sync.py` — accept a FHIR bundle +
  `actor_iss`/`actor_sub` (+ optional `person_id` for on-behalf-of), resolve Person via the existing
  identity path (`resolve_or_create_person` / `_resolve_person_from_identity`), reuse the `upload_fhir`
  mapping internally, return `person_id` + created ids. Permission: `ScopedTokenPermission`
  (`patient/*.write`), same as the lab-results sync view.
- **Service credential:** provision the `patient/*.write` OAuth2 bearer that `fhir_importers` presents
  as `CTOMOP_SERVICE_TOKEN` (same mechanism hk-labs uses), tied to the correct org.
- Optional: store `epic_patient_id` as a secondary external id on `Person` for provenance/dedupe
  (not the linkage key — identity is).

### 5.3 ht-phr — moderate wiring (simpler than before)
- **Frontend:**
  - Add `mychart_remote` to `frontend/vite.config.ts` remotes; env `VITE_MYCHART_REMOTE_URL`.
  - New `useMyChartApi()` (axios → `VITE_FHIR_IMPORTER_URL`, Firebase-token interceptor).
  - New *Connect MyChart* page + an Epic callback route rendering `mychart_remote/MyChartCallback`;
    sidebar nav entry. On sync complete, invalidate React Query caches for ctomop reads.
- **Backend:** none required for identity (JWT is forwarded; ctomop resolves Person). Optionally
  cache the returned `phr_person_id` for display convenience.
- **CI/deploy:** add `VITE_MYCHART_REMOTE_URL` + `VITE_FHIR_IMPORTER_URL` to `deploy-staging.yml`.

## 6. Phasing (incremental, each phase shippable)

- **Phase 0 — Django port + Identity adoption:** scaffold Django, port Epic OAuth modules, copy the
  Identity app + providers + PartnerAuthentication/ServiceTokenAuthentication, stand up Postgres.
  Existing `/epic/*` endpoints work, now authenticated by `(iss, sub)`. *(No user-visible change.)*
- **Phase 1 — Embed connector in ht-phr:** add `mychart_remote`, `useMyChartApi()`, Connect page +
  callback route. Epic SMART login works end-to-end inside the PHR (token still server-side only).
- **Phase 2 — Persistence + ctomop sync path:** `Connection`/`SyncJob`, encrypted token storage,
  ctomop `/api/fhir/sync/` endpoint + service credential, `CtomopSyncClient` posting a sample bundle.
  Proves the identity-resolved ingest path.
- **Phase 3 — Epic FHIR fetch:** `EpicFhirClient` with `$everything`, pagination, token refresh.
- **Phase 4 — Map + orchestrate + display:** FHIR→ctomop mapping for the decided first-cut scope
  (demographics + labs + conditions + meds), Celery sync + status endpoint, ht-phr polls and renders
  synced clinical data. **First full end-to-end demo.** (Oncology enrichment → issue #10, later phase.)
- **Phase 5 — Hardening:** token encryption/KMS, retries/backoff, idempotent re-sync, error surfacing,
  PHI security review, deploy wiring for staging; standalone-mode smoke test.

## 7. Resolved Decisions & Residual Risks

### Resolved decisions
- **Connector stack:** port `fhir_importers` to **Django/DRF**; copy ctomop's Identity stack verbatim.
- **First-cut mapping scope:** **demographics + labs + conditions + medications**. Oncology enrichment
  (ECOG, stage, ER/PR/HER2, therapy-line episodes) **deferred → issue #10**.
- **Ingest endpoint:** new dedicated **`POST /api/fhir/sync/`** in ctomop (mirrors `lab_results/sync.py`).
- **Service-to-service auth:** **same as hk-labs** — `actor_iss`/`actor_sub` in the body +
  `CTOMOP_SERVICE_TOKEN` (OAuth2 `patient/*.write` bearer); copy `ctomop_client.py`.
- **Deploy target:** **GCP Cloud Run** + Cloud SQL + Secret Manager, matching ht-phr/hk-labs.
- **Person provisioning:** non-issue — ctomop's `PartnerAuthentication` runs `_ensure_person` on every
  authenticated request, so the `Person` already exists (created on the patient's first `useCtomopApi`
  call) before any Epic sync. Sync resolves the same `(iss, sub)`; no duplicate.

### Residual risks (no longer blocking, manage during build)
- **Mapping fidelity for oncology:** the deferred enrichment (#10) is the main known limitation — until
  it lands, oncology-specific `PatientInfo` fields stay empty for Epic-sourced patients. Communicate this
  to clinical stakeholders so it isn't mistaken for missing data.
- **Idempotent re-sync:** re-running a sync must update, not duplicate, OMOP rows. ctomop's existing
  upsert keys (per measurement/condition/drug) should cover this; verify with a re-sync test in Phase 2.
- **Token security:** Epic refresh tokens are long-lived PHI-adjacent secrets — encrypted at rest
  (Fernet/KMS), never returned to the browser. Covered by design; verify in the Phase 5 security review.
- **Epic app registration (operational):** production Epic client id + redirect URIs must match
  ht-phr's hosted callback route per environment (dev/staging/prod) — an action item for whoever owns
  the Epic developer account, not a design fork.

## 8. Definition of Done

A patient logs into ht-phr, clicks *Connect MyChart*, completes Epic SMART login, and within one sync
sees their demographics, labs, conditions, and medications in the PHR — sourced from Epic, written to
ctomop's OMOP tables with `EHR_SYNC` provenance, linked to a single `Person` resolved from the shared
`(issuer, sub)` identity, with Epic tokens persisted (encrypted) only in `fhir_importers`, and re-sync
idempotent. `fhir_importers` runs as a platform Django service in both standalone and integrated modes.
```
