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
- **Service-to-service transport auth** for `/api/fhir/sync/`: reuse ctomop's existing
  `ServiceTokenAuthentication` (pre-shared bearer) or OAuth2 `client_credentials` (`ScopedTokenPermission`).
  Default: **OAuth2 client_credentials** (already used by `upload_fhir`, consistent and revocable).
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
- **FHIR → ctomop mapping (new):** normalize raw Epic FHIR into ctomop's expected bundle shape
  (LOINC Observations map cleanly; oncology-specific extensions are a known gap — see §7).
- **`CtomopSyncClient` (new):** obtain a ctomop `client_credentials` token; `POST` the bundle to
  `/api/fhir/sync/` with `actor_iss`/`actor_sub` and provenance `EHR_SYNC`; record results on `SyncJob`.
- **Orchestration (Celery, Django-native):** `/epic/auth/finish` persists `Connection` + enqueues a
  `SyncJob`. New endpoints: `GET /connections`, `POST /connections/{id}/sync` (re-sync),
  `GET /sync/{job_id}` (poll). All protected by `PartnerAuthentication` so a caller only sees their
  own Identity's connections.
- **Config:** ctomop base URL + client id/secret, Firebase project id, token-encryption key,
  `DATABASE_URL`, `PARTNER_AUTH_PROVIDERS`; CORS allows ht-phr origins.
- **Frontend remote:** keep `ConnectMyChart`/`MyChartCallback`; on `onSuccess`, poll
  `GET /sync/{job_id}` and show progress; optionally expose `MyChartConnections`. Tokens never
  surface to the host.

### 5.2 ctomop — small, additive
- **`POST /api/fhir/sync/` (new):** mirror `lab_results/sync.py` — accept a FHIR bundle +
  `actor_iss`/`actor_sub` (+ optional `person_id` for on-behalf-of), resolve Person via the existing
  identity path, reuse the `upload_fhir` mapping internally, return `person_id` + created ids.
  *(Alternative: extend `upload_fhir` to accept `actor_iss/actor_sub`; a dedicated endpoint is cleaner
  and matches the established sync pattern.)*
- **Service credential:** register an OAuth2 Application (or service token) for `fhir_importers`
  (`patient/*.write`, correct org); confirm org scoping for a non-user service client.
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
- **Phase 4 — Map + orchestrate + display:** FHIR→ctomop mapping, Celery sync + status endpoint,
  ht-phr polls and renders synced clinical data. **First full end-to-end demo.**
- **Phase 5 — Hardening:** token encryption/KMS, retries/backoff, idempotent re-sync, error surfacing,
  PHI security review, deploy wiring for staging; standalone-mode smoke test.

## 7. Risks & Open Questions

- **Mapping fidelity (biggest):** raw Epic FHIR lacks ctomop's custom extensions (ECOG, therapy-line,
  biomarkers); demographics/labs(LOINC)/conditions/meds map reasonably, oncology-specific `PatientInfo`
  fields won't populate without enrichment. Scope mapping explicitly; start narrow.
- **Django port effort:** rewriting the FastAPI broker is real work, but it is small (~10 files) and
  the port buys verbatim reuse of the identity stack + the future `healthkey-identity` package.
- **Token security:** Epic refresh tokens are long-lived PHI-adjacent secrets — encrypt at rest, never
  return to the browser (this design removes browser token custody).
- **fhir_importers gains state + infra:** Postgres + Celery + secrets (Epic private key, ctomop
  credential, encryption key). Confirm deploy target (current `.env` references a GCP/`healthkey-etl` context).
- **Epic app registration:** production client + redirect URIs must match ht-phr's hosted callback per env.
- **Person provisioning on first connect:** `_ensure_person` creates a `Person` from JWT claims with
  minimal demographics; confirm that is acceptable before the first Epic demographics arrive, and that
  re-sync updates (not duplicates) it.
- **Confirm:** dedicated `/api/fhir/sync/` endpoint vs. extending `upload_fhir` (plan recommends the
  dedicated endpoint), and service-token vs. client_credentials transport (plan recommends client_credentials).

## 8. Definition of Done

A patient logs into ht-phr, clicks *Connect MyChart*, completes Epic SMART login, and within one sync
sees their demographics, labs, conditions, and medications in the PHR — sourced from Epic, written to
ctomop's OMOP tables with `EHR_SYNC` provenance, linked to a single `Person` resolved from the shared
`(issuer, sub)` identity, with Epic tokens persisted (encrypted) only in `fhir_importers`, and re-sync
idempotent. `fhir_importers` runs as a platform Django service in both standalone and integrated modes.
```
