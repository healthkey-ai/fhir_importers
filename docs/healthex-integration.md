# HealthEx integration

[HealthEx](https://healthex.io) is a **patient-driven consent + data aggregation platform**. They handle the per-EHR fan-out (TEFCA via QHINs) and the patient identity/consent UI; we call a single FHIR endpoint and get a unified bundle.

**Status**: **production code path validated end-to-end against a real consenting patient on 2026-06-24.** fhir-importers side implemented (org-JWT auth, Unique Link onboarding, status polling, `healthex_patient_links` table). healthkey-etl extract DAG not yet built. Code change needed: re-introduce `add_patient` and call it before `get_unique_link` in `/healthex/connect` — this is the one architectural correction from the original design.

Last verified against the live API on **2026-06-24**.

Sources:
- [docs.healthex.io — Overview](https://docs.healthex.io/) · [Key Concepts](https://docs.healthex.io/key-concepts/) · [Authentication](https://docs.healthex.io/authentication/)
- [docs.healthex.io — FHIR Server](https://docs.healthex.io/fhir-server/) · [Patient Demographics](https://docs.healthex.io/patient-demographics) · [Data Retrieval Status](https://docs.healthex.io/data-retrieval-status)
- [docs.healthex.io — Adding Patients to Projects](https://docs.healthex.io/add-patients-to-projects/) · [Add Patients by Unique Link](https://docs.healthex.io/add-patients-to-projects/add-patients-by-unique-link)
- [docs.healthex.io — API reference](https://docs.healthex.io/api) · [getPatientConsents](https://docs.healthex.io/api/get-patient-consents) · [Test Patients](https://docs.healthex.io/test-patients) · [Sample Patients](https://docs.healthex.io/sample-patients/)
- [docs.healthex.io — MCP Server](https://docs.healthex.io/mcp-server/)
- [Sequoia — Designated QHINs](https://rce.sequoiaproject.org/designated-qhins/) (HealthEx is **not** on this list)

## Environments

Per Diana Cristea's kickoff email (2026-06-09), HealthEx provisions **two separate organizations** per customer — each is its own `organizationId` with its own API credentials:

| Env | Host | Notes |
|---|---|---|
| Sandbox | `healthtree.test.healthex.io` | Safer for first runs; isolated org |
| Production | `healthtree.healthex.io` | Real outreach fires here |

Each user who needs both must have two distinct emails — recommended pattern: `user@healthtree.org` for prod, `user+sandbox@healthtree.org` for sandbox (Gmail/Outlook `+` aliasing supported).

**Current `.env` credentials point at production.** Sandbox credentials TBD (waiting on Diana to provision).

HealthEx contacts:
- Diana Cristea (`diana.cristea@healthex.io`) — Commercial Intern, our liaison
- Support: `support@healthex.io`

## How HealthEx differs from MyChart/Epic

| Concern | MyChart / Epic (existing) | HealthEx |
|---|---|---|
| Who owns the user↔hospital linkage | We do, via `mychart_connections(user_uid, organization_alias)` | HealthEx does — invisible to us |
| Auth | SMART-on-FHIR per-patient OAuth + JWT private_key_jwt + Fernet-encrypted refresh tokens | **Org-level API key + secret → 24h JWT bearer**, one credential for all consented patients |
| Per-tenant PEM / JWKS kid | Yes | None |
| Per-user state | 3 encrypted tokens + refresh lifecycle | Just `healthex_patient_id` (UUID) + status |
| Race-safe refresh | `SELECT FOR UPDATE` on connection row | Not needed — JWT is process-cached |
| Onboarding shape | Redirect → Epic UI → callback to `/auth/finish` with auth code → exchange for tokens | API call to addPatients → mint Unique Link → user opens in browser → consents on healthex.io; **no callback** — we discover state by polling |
| Knowing when data is ready | Always immediate post-token | **Asynchronous** — poll `getPatientConsents` until `patientId` resolved, then optionally poll `data-retrieval-status` |
| Primary fetch | `GET /Patient/{id}/$everything` against org's Epic endpoint | `GET /FHIR/R4/Person/{patientId}/$everything` against `api.healthex.io` |
| FHIR version | DSTU2 / STU3 / R4 (per org) | R4 only |
| Bulk `$export` NDJSON | Yes (`fhir_bulk_extract`) | Not exposed |
| Incremental sync | We compute `_since` from `last_synced_at` | Native `?_since=<ts>` (timestamp-filtered, not guaranteed minimal delta — keep dedup ledger) |
| Consent enforcement | Implied by token possession | HealthEx-side, per-Project; org JWT only sees patients consented to projects we own |
| Push (webhooks) | Not applicable | **None** — pull-only, polling required |

**UX-level the integration looks identical to MyChart**: user clicks "Connect HealthEx" → goes to HealthEx UI → authenticates + consents → we can fetch their data. The difference is internal: we hold one org credential, not per-patient tokens.

## Production code path (end-to-end, live-verified 2026-06-24)

```
1.  POST /v1/auth/token                         → org JWT (HTTP 201)
2.  POST /v1/projects/{id}/patients             → addPatients (REQUIRED — creates Recruitment record)
3.  POST /v1/projects/{id}/link                 → mint Unique Link (HTTP 201, text/html body)
4.  [user opens link in browser]
5.  [user signs in with CLEAR / Google / Microsoft]
6.  [user grants consent]
7.  GET  /v1/patients/consents?externalId&projectId  → patientId once OPTED_IN
8.  GET  /FHIR/R4/Person/{patientId}/$everything    → Bundle
```

Steps 1, 2, 3, 7, 8 are server-side from our backend (org JWT). Steps 4–6 happen in the user's browser on HealthEx-hosted UI; we never see credentials.

## Auth flow

`POST https://api.healthex.io/v1/auth/token` returns the org JWT. **Live-verified shape**:

- Headers: `Content-Type: application/json`, `Accept: application/json`
- Body: `{"apiKey": "<key>", "apiSecret": "<secret>"}`
- **HTTP 201** (not 200) on success
- Response: `{"token": "<jwt>", "expiration": <absolute_unix_epoch_seconds>}`
- JWT decoded claims include `organizationId`, `permissions` (e.g. `[ORG_ADMIN]`), `type` (e.g. `API_EXTERNAL_RESEARCHER`)

→ **No separate `HEALTHEX_ORG_ID` env var needed** — derive from JWT if/when wanted.

Token caching is in-process with a 60s skew before the server-reported `expiration`. Refresh is gated by an `asyncio.Lock` to avoid bursting `/auth/token` on parallel cache misses.

## URL surface

HealthEx uses both `/v1/projects/` and `/v1/studies/` inconsistently across endpoints. Live-verified URLs:

| Operation | URL |
|---|---|
| Mint org JWT | `POST /v1/auth/token` |
| addPatients (creates Recruitment) | `POST /v1/projects/{projectId}/patients` |
| getProjectLinkForPatient (Unique Link) | `POST /v1/projects/{projectId}/link` |
| **getPatientConsents** (externalId → patientId) | `GET /v1/patients/consents?externalId={uid}&projectId={pid}` |
| has-patient-consented-to-study (yes/no check only) | `GET /v1/patients/consented/study/{studyId}/{consentType}?externalId={uid}` |
| getPatientDemographics | `GET /v1/projects/{projectId}/patients/{patientId}/demographics` |
| getStudyById | `GET /v1/studies/{studyId}` |
| FHIR `$everything` | `GET /FHIR/R4/Person/{patientId}/$everything` |
| Test patients (create/list) | `POST /v1/organizations/{orgId}/test-patients` |
| Consent record by ID | `GET /v1/consents/{consentRecordId}` |

The org JWT is required for all of these. **There is no FHIR SMART-on-FHIR discovery** (`/FHIR/R4/.well-known/smart-configuration` returns 404 even with valid auth) — the CapabilityStatement security block declares: *"Use HealthEx API keys for authorized access to FHIR APIs"*.

## Data model

- **Project** (aka "study" in some URLs) — the unit of purpose ("breast cancer registry", "MM cohort"). Every patient is added to a project; consent is per-project, not per-org.
- **Recruitment** — HealthEx's internal name for "we're expecting this externalId to consent to this study". Created by `addPatients`. Required for the Unique Link flow to bind a signed `xid` back to our org (without it, the patient-side `link-identified-patient` call returns 404 "Recruitment not found").
- **Patient** — gets a HealthEx UUID (`patientId`) when the user signs in (Google/Microsoft/CLEAR account creation). Linked to the Recruitment via `link-identified-patient`.
- **Consent** — two types: **Data Authorization** (access via healthcare organizations) and **Patient Directed Data Exchange** (access via public data networks, i.e. TEFCA). Granular scopes by FHIR resource type + sensitivity category. **For consumer-app integration, the relevant consent type is `PATIENT_DIRECTED_DATA_EXCHANGE`.**

The Unique Link → consent flow creates **two consent records per patient/project** (observed live):
1. "I allow HealthEx ongoing access to my records" → consent to HealthEx the platform
2. "I authorize HealthEx to share my records with HealthTree" → consent to our org

## Onboarding: Unique Link (production path)

HealthEx supports three onboarding shapes. Only **Unique Link** is the right fit for a consumer app where users initiate the connection themselves:

| Shape | Use case | Fits us? |
|---|---|---|
| **Generic Link** (one URL per project, no externalId) | Public study recruitment | No — we can't tie a consent back to a user |
| **Unique Link** (per-patient URL with externalId + signature) | Consumer app integration | ✅ **This** |
| **addPatients API** (`POST /v1/projects/{id}/patients`, batch) | Org-initiated outreach (email/SMS via HealthEx) | Required as a step in the Unique Link flow too — see below |

### addPatients is REQUIRED before minting Unique Link

The docs at `/add-patients-to-projects/add-patients-by-unique-link/` claim Unique Link works standalone, but **empirically that is false**. Without a prior `addPatients` call, the user's browser-side `link-identified-patient` step at consent time returns `404 "Recruitment not found"`.

**Live-verified addPatients body**:

```json
POST /v1/projects/{projectId}/patients
{
  "patients": [{
    "externalId": "<user_uid>",
    "email": "<user email>",
    "firstName": "<first>",
    "lastName": "<last>",
    "languagePreference": "en",
    "contactPreference": "email"
  }],
  "suppressNotifications": true
}
```

Required fields: `externalId`, `contactPreference` (`"email"` or `"phone"`). `suppressNotifications: true` skips HealthEx-managed outreach (our flow already has a user-initiated click; no need for them to send email/SMS).

Response: `{totalProcessed, successCount, errorCount, duplicatesCount, errors, duplicates, successfulPatients}`. **Does not return `patientId`** — that's not assigned until the user signs in.

### Mint the link (live-verified)

`POST https://api.healthex.io/v1/projects/{projectId}/link`

- Body: `{"externalId": "our-user-uid"}`. Omit `externalId` to get a generic link.
- **HTTP 201**, `Content-Type: text/html`, body is the **raw URL as a string** (NOT JSON)
- Returned URL format: `https://app.healthex.io/#/patient-consent/{projectId}/enrollment/link?xid={externalId}.{signature}`

The `xid` carries our externalId concatenated with a server-generated HMAC-style signature. **Cannot be constructed client-side** — docs explicitly say *"links are generated with a cryptographic signature. Do not attempt to construct your own links!"*

### After the user clicks the link

HealthEx hosts the onboarding UI at `app.healthex.io`. It offers three sign-in/verification options:

| Option | Identity assurance | Notes |
|---|---|---|
| **Continue with CLEAR** | NIST IAL2/AAL2 (gold standard for TEFCA record retrieval) | **US-only**: returns *"HealthEx does not allow verifications from your current location"* for non-US runners |
| **Continue with Google** | Google account + US phone OTP | **Works for non-US developers** (Nikita verified). Sufficient to complete consent and resolve patientId; whether it unlocks the same record-retrieval scope as CLEAR is unverified |
| **Continue with Microsoft** | Microsoft account + US phone OTP (presumed) | Untested |

In the patient's browser, after consent, HealthEx fires `POST /patients/{patientId}/studies/{projectId}/link-identified-patient` with body `{signedExternalId: "<xid>"}`. This is what binds the just-authenticated Patient to our Recruitment. We don't call this ourselves; it's HealthEx's frontend flow.

**No callback to us.** We discover the patient state by polling `getPatientConsents`.

### Externalid → patientId lookup (live-verified)

`GET https://api.healthex.io/v1/patients/consents?externalId={uid}&projectId={projectId}`

- Always HTTP 200 once the patient exists in HealthEx's system (even if not yet consented to our project).
- Response shape:
  ```json
  {
    "total": <int>,
    "results": [
      {
        "consentRecord": {
          "id": "<uuid>",
          "patientId": "<uuid>",
          "studyId": "<uuid>",
          "consentType": "PATIENT_DIRECTED_DATA_EXCHANGE",
          "consentStatus": "OPTED_IN",
          "expirationTimestamp": "<iso>",
          "consentDataResourceScopes": [18 categories: MEDICATIONS, LABS, ...],
          "consentedByLink": true,
          ...
        }
      }
    ]
  }
  ```
- Our client iterates `results[].consentRecord` and returns `patientId` from the first record where `consentType=PATIENT_DIRECTED_DATA_EXCHANGE` AND `consentStatus=OPTED_IN`.

**Eventual consistency note**: the HealthEx UI shows "Active" before the consents table is fully readable via API. Observed ~30s lag in one test. Poll with patience.

The older `has-patient-consented-to-study?externalId=` endpoint at `/v1/patients/consented/study/{studyId}/{TYPE}` is a yes/no consent check that does NOT return `patientId` — easy to confuse with the patient-lookup endpoint above; use `getPatientConsents` instead.

## FHIR API surface (live-verified)

- **Base**: `https://api.healthex.io/FHIR/R4/`
- **CapabilityStatement**: `fhirVersion 4.0.1`, 146 resource types exposed
- **Primary endpoint**: `GET /Person/{patientId}/$everything` — returns a unified Bundle. Live-verified end-to-end against a real consenting patient: HTTP 200, valid Bundle of `type: searchset`.
- **Empty-data case**: when the patient has not linked any hospital in the consent flow, the bundle has 2 entries (Person + Patient with demographics). No clinical resources. Endpoint works; just no upstream EHR to pull from.
- **Paging**: `_count` + `_offset`. Streaming responses for large bundles.
- **Filtering**: `_type=Observation,Condition` to limit resource classes.
- **Delta**: `_since=<timestamp>` — returns resources **updated** (not strictly **new**) since T. Docs recommend recording the timestamp at call-start; keep our `pushed_resources` ledger for dedup.
- **No `$export`**.

## TEFCA / QHIN topology

HealthEx is **not** a Designated QHIN. They connect through:
- **MedAllies** (Designated QHIN)
- **CommonWell Health Alliance** (Designated QHIN)

Data freshness depends on those QHINs' upstream connectors (and ultimately on each EHR's TEFCA-exposed FHIR endpoint). Coverage claims ("80% of U.S. providers") are inherited from the QHINs, not direct.

## Test patients (the CI / no-browser test affordance)

HealthEx exposes synthetic test patients deliberately to enable automated testing. They:
- Have `isTestPatient: true` flag
- Get auto-generated email `test-patient+<random>@<org-domain>` and password
- **Bypass CLEAR entirely** — log in via the standard `/v1/auth/token` (with `{email, password}` body) like any patient

`POST /v1/organizations/{orgId}/test-patients` (live-verified):
- Body: `{"firstName": "...", "lastName": "...", "dateOfBirth": "..."}` (all optional)
- **HTTP 201** → returns `{id, email, password, firstName, lastName, dateOfBirth, organizationId, createdAt, isTestPatient: true}`
- **Password is shown ONCE at creation.** Save it immediately; cannot be retrieved later.

### Where the `<org-domain>` is set

The `<org-domain>` for test-patient email generation lives **inside the SSO setup form** — the "Email Domain Name *" required field. Same value powers both the SSO email-suffix matcher AND the test-patient email auto-generator.

For our prod org, the domain was set to `healthtree.org` by HealthEx admin on 2026-06-24 (we didn't enable SSO; they set the field on the backend). The "Custom HealthEx URL" setting in the admin UI is unrelated — that's the patient-portal subdomain (e.g. `healthtree.healthex.io`), not the email domain.

### Test patients vs production code

| | Production code path | Test-patient path (CI only) |
|---|---|---|
| Patient credentials | **Never seen by us** — HealthEx handles CLEAR/Google/Microsoft auth | We hold the synthetic patient's email + password |
| CLEAR required | Yes for real users; Google/Microsoft alternatives exist | No — test patients bypass identity verification by design |
| Where it's exercised | `/healthex/connect` endpoint | `test_healthex_patient_auth.py` (dev-only script) |
| What it validates | Full production flow (manual, needs browser + real ID) | Auth + consent + `$everything` pipeline (deterministic, no browser) |

**Production code never collects patient passwords.** Same shape as MyChart in that respect.

## Sample patients

125 Synthea-generated bundles, no consent flow needed. Access gated by emailing `partnersupport@healthex.io`. Best path for fast `$everything` smoke testing against rich synthetic data; we don't have access yet.

## MCP server (separate surface — not our integration target)

HealthEx hosts an MCP server at `/mcp` (JSON-RPC 2.0) that AI agents authenticate against with per-patient OAuth 2.0 + PKCE. Designed for chatbots (Claude, ChatGPT) to query a patient's record on demand with natural-language ranking. Not the right fit for batch OMOP ingest — for our pipeline, use the FHIR server with the org JWT.

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
| `test_healthex_flow.py` | Manual e2e smoke of the production path: mints link → `breakpoint()` → user clicks link, completes consent → polls patientId → polls status → GETs `$everything` |
| `test_healthex_patient_auth.py` | Automated test-patient flow: patient JWT → add to project → opt-in consent → `$everything`. No browser, no CLEAR. Needs `HEALTHEX_TEST_PATIENT_*` env vars |
| `create_patient.py` | Standalone: addPatients (suppressNotifications=true) → mint Unique Link. Used to test the addPatients-first hypothesis; useful template for the production `/healthex/connect` flow |
| `verify_consent.py` | Resolve externalId → patientId via getPatientConsents → dump raw consent record → GET `$everything` |
| `pull_patient.py` | One-shot `$everything` pull by patient_id (with optional `--since`) |
| `debug_consent.py` | Diagnose endpoint differences (parametric consent-type vs list endpoints) |
| `repro_healthex_test_patient_400.py` | Minimal repro of the "domain not configured" 400 (now succeeds — patient creation works) |

State machine for `healthex_patient_links.status`:
```
PENDING_CONSENT → RETRIEVAL_IN_PROGRESS → COMPLETE
                                       └→ ERROR
                       (any state)     → REVOKED
```

## ctomop write path — open architectural question

`/api/fhir/sync/` (Vlad's PR #106, merged Jun 1) is a per-patient bulk endpoint in ctomop that accepts a FHIR Bundle and writes everything in one transaction with PatientInfo refresh deferred by design. There's also `/api/patient-info/upload_fhir/?skip_refresh=true` (Adam's commit `83aea20`) — accepts a Bundle with explicit refresh control. **Per-resource endpoints (`/api/conditions/`, `/api/measurements/`, etc.) do not expose any refresh-skip mechanism.**

Our `CtomopApiOmopWriter` currently calls the per-resource endpoints, so we hit refresh-per-call slowness. Three migration paths:

1. **Delegate parsing to `/api/fhir/sync/`** — POST raw FHIR bundles, skip our `services/fhir_parsing/` for ctomop ingest. Fastest. Risk: ctomop's parser may not match ours on edge cases.
2. **Ask Adam/Vlad for a new endpoint accepting structured rows** — preserves our parser's value, atomic per patient, one refresh. Bigger ctomop PR.
3. **Stay on per-resource endpoints, ask for `?skip_refresh=true` on them too** — incremental, still pays N HTTP roundtrips per patient.

Not yet decided — needs Adam's input on which fits ctomop's evolution.

## Code changes still needed (fhir-importers)

- **Re-introduce `HealthExClient.add_patient`** — was removed earlier when we thought Unique Link was standalone. Body shape per "addPatients is REQUIRED" section above.
- **Update `POST /healthex/connect`** to call `add_patient` before `get_unique_link`. Order: addPatients → mint link → persist + return link.

## What's still needed (healthkey-etl side, not yet built)

- **Token provider** mirroring `app/healthex_client.py::HealthExClient` (same auth flow, async httpx).
- **Status-polling DAG** `fhir_healthex_poll_status` — periodic scan over `healthex_patient_links` rows in `PENDING_CONSENT` / `RETRIEVAL_IN_PROGRESS`, calls `find_patient_id_by_external_id`, writes resolved `healthex_patient_id` + status back. Fires the extract DAG on transition. Replaces the role MyChart's `/auth/finish` callback played.
- **Extract DAG** `fhir_extract_healthex(user_uid, healthex_project_id, healthex_patient_id)` — get JWT → `GET $everything?_since=…` → hand to existing `ingest_artifact` (OR migrate to `/api/fhir/sync/` per the ctomop write-path decision above).
- **Reuses untouched**: FHIR R4 parser (`services/fhir_parsing/`), `OmopWriter`, `pushed_resources` idempotency ledger, ctomop HTTP client.

## Known unknowns / open questions

1. **`get_data_retrieval_status` URL still unverified.** `GET /v1/patients/data-retrieval/status` returns HTTP 403 "Forbidden resource" with our org-JWT (`API_EXTERNAL_RESEARCHER` role). The code path is left in but soft-fails through to `$everything`. May be role-restricted; may need different URL — ask Diana.
2. **Google sign-in scope vs CLEAR** — does Google sign-in unlock the same record-retrieval rights as CLEAR-verified accounts, or is it a separate tier with limited access? Real test requires linking a real hospital to a Google-authed patient.
3. **CLEAR alternatives for international devs** — can a non-CLEAR identity-verification path be enabled for sandbox? Google works empirically but requires US phone OTP; not a true non-US path.
4. **Rate limits + burst caps** — not documented.
5. **`_since` exact semantics** — docs say "updated since T" without specifying whether trivial server-side touches bump the timestamp. Empirical test required; our ledger covers us either way.
6. **`/v1/studies/{id}` returns HTTP 200 with empty body** for our project. Authorization-scoped maybe. Not blocking.
7. **Two consent records per patient** — `total=2` observed live. One is platform-level (HealthEx access), one is org-level (sharing with HealthTree). Confirm with Diana that this is expected and that querying the org-level one (PATIENT_DIRECTED_DATA_EXCHANGE / OPTED_IN) is correct.

## Coverage caveat

HealthEx claims aggregation from "over 80% of U.S. care providers". This is **marketing**; actual coverage is inherited from MedAllies + CommonWell. Verify against our target hospitals before treating HealthEx as a replacement for direct Epic SMART integration. The two paths likely **coexist** — HealthEx for breadth, direct Epic for specific institutional partnerships and richer scopes.
