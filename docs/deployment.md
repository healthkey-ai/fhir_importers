# Deployment

## Image

Built and pushed to GCP Artifact Registry by GH Actions on merge to `main`. Single image carries the multi-stage-built federation remote + FastAPI backend. Build sketch lives in [`frontend-remote.md`](frontend-remote.md).

## Runtime

`deploy/docker-compose.yaml` on the remote host. Services:

| Service | Role |
|---|---|
| `app` | FastAPI + the federation remote (single container) |
| `postgres` | `mychart_connections` storage |
| `redis` | OAuth `state` store |
| `migrate` | One-shot; runs `alembic upgrade head` before `app` starts |

Bound to `0.0.0.0:8030` on the host. Traefik / TLS is out of scope for this iteration — the deploy environment provides a reverse proxy.

## Env

Categorized by concern; pointers go to the file that explains each one.

**Storage** ([`token-management.md`](token-management.md)):
- `DATABASE_URL` — async URL for FastAPI's SQLAlchemy; the `migrate` service rewrites it to a sync URL for Alembic.
- `REDIS_URL` — OAuth state store.

**Identity / auth** ([`token-management.md`](token-management.md), [`DATA_FLOW.md`](DATA_FLOW.md)):
- `FIREBASE_PROJECT_ID` — used to derive the verifier issuer.
- `FIREBASE_CREDENTIALS_PATH` — service account JSON path (optional; falls back to ADC or emulator).
- `TOKEN_ENCRYPTION_KEY` — Fernet key; SHALL match healthkey-etl.

**Epic OAuth** ([`token-management.md`](token-management.md)):
- `STAGING_PRIVATE_KEY_PATH`, `PROD_PRIVATE_KEY_PATH`, `STAGING_JWKS_KID`, `PROD_JWKS_KID`, `STAGING_CLIENT_ID`, `PROD_CLIENT_ID`, `STAGING_REDIRECT_URI`, `PROD_REDIRECT_URI`.

**Orchestration** ([`healthkey-etl-integration.md`](healthkey-etl-integration.md)):
- `AIRFLOW_URL`, `AIRFLOW_USERNAME`, `AIRFLOW_PASSWORD`.

**Frontend** ([`frontend-remote.md`](frontend-remote.md)):
- `REMOTE_BUNDLE_DIR` — path to the built federation remote (defaults to image location).
- `CORS_ALLOWED_ORIGINS` — comma-separated origin list.

**Bootstrap**:
- `POSTGRES_PASSWORD` — only set on first boot to initialise the DB; subsequent restarts use `DATABASE_URL` and may omit it.

## Post-deploy smoke

CI waits for `/health`, then runs `make smoke` against the live deploy. Smoke failure SHALL fail the deploy job.
