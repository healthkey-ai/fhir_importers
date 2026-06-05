# Token management

fhir-importers is the sole writer for the `mychart_connections` table: it acquires Epic tokens through the OAuth handshake, encrypts them at rest, and triggers the downstream pipeline. healthkey-etl is the only other party that touches these tokens — it reads them and performs refresh per the cross-service contract.

Cross-service contracts referenced throughout:
- Token cipher: [`DATA_FLOW.md`](DATA_FLOW.md)
- Token refresh + lock: [`DATA_FLOW.md`](DATA_FLOW.md)
- Private-key JWT material contract: [`DATA_FLOW.md`](DATA_FLOW.md)

## mychart_connections schema

Keys:
- `id` — auto-increment surrogate.
- `(user_uid, organization_alias)` — natural key (UNIQUE).
- `last_synced_at` — informational timestamp; not a watermark ([`DATA_FLOW.md`](DATA_FLOW.md)).

Token columns (`access_token`, `refresh_token`, `id_token`) hold Fernet ciphertext. Plaintext SHALL NEVER be persisted or logged.

Schema lifecycle: managed via Alembic in `migrations/`. New columns SHALL ship with a migration; the deploy compose runs `migrate` as a one-shot service before `app` starts.

The shared-DB exception ([`DATA_FLOW.md`](DATA_FLOW.md)) means healthkey-etl reads + updates the token columns and `last_synced_at`. New columns relevant to refresh or sync (e.g. a `needs_reauth` status) SHALL be coordinated with healthkey-etl's repository layer — see [`healthkey-etl-integration.md`](healthkey-etl-integration.md).

## Identity persistence

The `mychart_connections.user_uid` column is the only durable record of the patient's identity in this system. Its content is the verified Firebase `sub` claim, captured during `/auth/finish` via `BaseTokenVerifier`. Everything downstream — token refresh by healthkey-etl, the ctomop Person key — derives from it.

The chain:

1. fhir-importers verifies the Firebase ID token on `/auth/finish` and `/connections/{alias}/sync`.
2. The verified `sub` (= `user_uid`) is persisted on `mychart_connections.user_uid`.
3. healthkey-etl later reads that row and reconstructs the Firebase tuple `(iss, sub)` to pass to ctomop's `resolve_or_create_person` ([`../healthkey-etl/ctomop-integration.md`](../healthkey-etl/ctomop-integration.md)).
4. ctomop returns the same `person_id` regardless of which Epic org triggered the sync — that's how multi-org merge works.

**Implications**:

- fhir-importers SHALL NOT accept connections from anonymous callers or callers without a verifiable Firebase identity. The chain depends on `(iss, sub)` being trustworthy at the point of persistence.
- If verification ever moves to a non-Firebase IdP, this schema SHALL grow an explicit `actor_iss` column to disambiguate (see [`DATA_FLOW.md`](DATA_FLOW.md) → Contract evolution). Until then, `iss` is implicit (one Firebase project per deploy).
- This schema SHALL NOT add any column or behavior that ctomop's resolve-or-create logic depends on — the boundary between identity provider (us) and patient store (ctomop) is the Firebase tuple, nothing more.

## /auth/start handler

1. Validate `alias` against `organizations.json`.
2. Run SMART discovery via `BaseEpicClient` (fetch `.well-known/smart-configuration`).
3. Generate PKCE `code_verifier` + `code_challenge` (`S256`).
4. Generate cryptographic `state` (≥256-bit random).
5. Persist `PendingState{alias, code_verifier}` in Redis under `state` key with TTL ≤10 min.
6. Build `authorization_url` (with `client_id`, `redirect_uri`, `scope`, `code_challenge`, `code_challenge_method=S256`, `state`, `aud`).
7. Return `{authorization_url, state}`.

This endpoint is unauthenticated; rationale in [`api.md`](api.md).

## /auth/finish handler

1. Verify Firebase JWT; capture `user_uid`.
2. Atomically consume the Redis state — single `GETDEL`, no read-then-delete.
3. If state missing / expired: 400.
4. Build `client_assertion` (RS256 JWT signed with per-tenant private key — see § Private-key JWT material below).
5. POST to Epic `token_endpoint` with `grant_type=authorization_code` + `code` + `code_verifier` + `client_assertion`.
6. On Epic `invalid_grant`: 400 proxied (original code expired or replayed).
7. On Epic 5xx: 502; client SHOULD retry.
8. Encrypt access_token + refresh_token + id_token via the configured cipher.
9. UPSERT into `mychart_connections` keyed by `(user_uid, alias)` — re-OAuth replaces existing tokens.
10. Fire DAG trigger ([`healthkey-etl-integration.md`](healthkey-etl-integration.md)); failures SHALL be logged and swallowed.
11. Return metadata only — never tokens.

## Private-key JWT material

Per-tenant PEM files, signed RS256:

| Tier | Private key path env | `kid` env |
|---|---|---|
| Sandbox (`my_chart_central`) | `STAGING_PRIVATE_KEY_PATH` | `STAGING_JWKS_KID` |
| Production (other orgs) | `PROD_PRIVATE_KEY_PATH` | `PROD_JWKS_KID` |

Both files SHALL be mounted at deploy time. The corresponding JWKS (public key) is hosted publicly so Epic can verify signatures; generation is via `make_jwks.py`.

The same key files and `kid` env vars SHALL be deployed alongside healthkey-etl (which uses them for refresh). Drift between the two services' keys produces silent `invalid_client` errors at Epic.
