# API

The endpoint inventory and contract — paths, request/response shapes, status codes — live in [`../openapi.yaml`](../openapi.yaml). This document covers what's *around* the contract: framework, dependency injection, middleware, logging, error shaping, and the cross-cutting policies that don't fit per-handler docs.

Per-handler implementation details:
- OAuth handlers (`/auth/start`, `/auth/finish`) → [`token-management.md`](token-management.md)
- `/sync` handler + DAG trigger → [`healthkey-etl-integration.md`](healthkey-etl-integration.md)

## Framework

FastAPI on `app/main.py` with an `asynccontextmanager` lifespan that builds the dependency graph and attaches it to `app.state`. Handlers consume each piece via FastAPI `Depends(...)`.

| State key | Built from | Used by |
|---|---|---|
| `organizations` | `OrganizationRegistry.from_file(ORGANIZATIONS_FILE)` | `/epic/organizations`, `/auth/start` |
| `epic_auth_service` | `EpicAuthService(EpicClient, RedisStateStore, ...)` | `/auth/start`, `/auth/finish` |
| `db_sessionmaker` | async SQLAlchemy session factory | request-scoped via `get_connections_repo` |
| `token_cipher` | `TokenCipher(TOKEN_ENCRYPTION_KEY)` | every `mychart_connections` read/write |
| `token_verifier` | `FirebaseTokenVerifier` | `get_current_user_uid` |
| `airflow_client` | `AirflowClient(httpx, AIRFLOW_*)` | `/auth/finish`, `/sync` |

Every collaborator behind an ABC: `BaseConnectionsRepository`, `BaseAirflowClient`, `BaseTokenCipher`, `BaseTokenVerifier`, `BaseEpicClient`, `BaseStateStore`. In-memory fakes for each are a one-line swap — tests and CLI tools bypass the lifespan and wire concrete classes directly.

The lifespan also owns the lifecycles of the shared `httpx.AsyncClient`, the Redis client, and the async SQLAlchemy engine — all closed on shutdown.

## Middleware

Only one application-level middleware: **`CORSMiddleware`**.

- Origins: `CORS_ALLOWED_ORIGINS` env var, comma-separated.
- `allow_credentials=False`.
- Methods: `GET POST DELETE OPTIONS`.
- Headers: `Content-Type Authorization`.
- Applies to both the JSON API and the `/remote` static mount, so the host SPA can fetch the federation entry across origins.

FastAPI's built-in stack handles request-body validation (raising 422 with `HTTPValidationError`) and exception → JSON conversion.

## Static mount

`/remote` is mounted as `StaticFiles(directory=REMOTE_BUNDLE_DIR)`. If the directory is missing at startup, the mount is skipped and a warning logged — `/health` and the JSON API still respond. Build details: [`frontend-remote.md`](frontend-remote.md).

`mimetypes.add_type("application/javascript", ".mjs")` runs at import time so `.mjs` chunks served from `/remote` get a Content-Type a browser will accept as an ES module.

## Error response shapes

- `raise HTTPException(status_code, detail="…")` → `{"detail": "<string>"}`. This is what every handler-raised 4xx/5xx in this service produces.
- Pydantic request-body / path-param validation failure → 422, body `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` (FastAPI's `HTTPValidationError`).
- Unhandled exception → 500 with FastAPI's default body.

The two shapes differ; SDK generators consuming [`../openapi.yaml`](../openapi.yaml) should generate separate exception classes for `Error` and `HTTPValidationError`.

## Logging

Module-level config in `app/main.py`:

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
```

Per-request structured fields (notably `trace_id`) are documented in [`observability.md`](observability.md). Handler-side exception logging uses `_logger.exception(...)` which captures the traceback into the log record.

## Cross-cutting policies

### Auth boundary

`GET /health`, `GET /epic/organizations`, and `POST /epic/auth/start` are public. Every other endpoint SHALL verify `Authorization: Bearer <Firebase ID token>` per request via `BaseTokenVerifier` (contract: [`DATA_FLOW.md`](DATA_FLOW.md)). The verified `sub` is the connection-owner key.

`/auth/start` is intentionally public: `state` is opaque random and the auth gate is at `/finish`, where the connection is claimed for the authenticated `user_uid`. The OAuth flow can therefore be initiated before the host SPA has acquired its own bearer token.

### Cross-user access

Connection list / delete / sync SHALL filter on the verified `user_uid`. A caller accessing another user's connection SHALL receive 404, not 403, to avoid existence-leak.

### OAuth-specific error mapping

Cross-service idempotency + concurrency properties live in [`DATA_FLOW.md`](DATA_FLOW.md).

| Condition | Surface | Retry |
|---|---|---|
| `state` expired / replayed | 400 | no — reinitiate |
| Epic `invalid_grant` on `/finish` | 400, proxied | no — reinitiate |
| Epic 5xx on `/finish` | 502 | client SHOULD retry |
| DAG trigger fails (on `/finish`) | logged, swallowed | yes — via re-sync |
| DAG trigger fails (on `/sync`) | 502 | client SHOULD retry |
| Token persistence fails | 500 | client SHOULD retry; idempotent |
