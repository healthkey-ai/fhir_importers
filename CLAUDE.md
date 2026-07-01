# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this service is

`fhir-importers` is a **FastAPI microservice bundled with a Vite Module-Federation remote** in a single Docker image. It brokers two independent patient-data acquisition flows on behalf of a host SPA (`ht-phr`):

- **Epic SMART-on-FHIR** — per-patient OAuth. Handler mints per-user access + refresh tokens, stores them Fernet-encrypted in `mychart_connections`.
- **HealthEx** — TEFCA aggregator (MedAllies + CommonWell QHINs). Org-level API key + secret → 24h JWT; one credential fans out to every consented patient. Row in `healthex_patient_links` tracks status per (user, project).

**This service does not pull FHIR data itself.** It handles OAuth / consent, persists tokens or link rows, and triggers Airflow DAGs (`fhir_extract`, `healthex_extract`) that live in a sibling repo (`healthkey-etl`) to do the actual pull → parse → OMOP ingest. See `docs/DATA_FLOW.md` for the cross-service sequence.

## Key architectural conventions

- **DI via abstract base classes** (`app/auth.py:BaseTokenVerifier`, `app/connections.py:BaseConnectionsRepository`, `app/healthex_links.py:BaseHealthExLinksRepository`, `app/airflow.py:BaseAirflowClient`, `app/client.py:BaseEpicClient`). Route handlers depend on the ABC; production wires up the concrete impl in `app/main.py` lifespan; tests use in-memory fakes from `tests/fakes.py` or `create_autospec(Base…, instance=True, spec_set=True)`.
- **Env-var reads centralized in `services/service_locator.py`.** `load_dotenv()` is called there and nowhere else. Do not add `os.environ.get(...)` inside route handlers or client classes — instantiate via the service locator so a single call site owns the config surface.
- **HealthEx protocol knowledge lives in `services/healthex_client.py` only.** Every HealthEx URL, request body shape, and response parse happens in that one class. Delivery layers (FastAPI routes, CLI, tests) call typed methods; they never construct HealthEx URLs. Same discipline applies to `EpicClient` for Epic.
- **Two sibling routers, mirrored:** `app/routers.py` (Epic, prefix `/epic`) and `app/healthex_routers.py` (HealthEx, prefix `/healthex`). When adding a HealthEx endpoint, look at the Epic counterpart first — e.g. `_dag_run_prefix` / `_dag_conf` helper pattern (`app/routers.py:39,43` mirrored in `app/healthex_routers.py`). Cross-router drift is a smell.
- **Async everywhere for runtime, sync only for alembic.** `asyncpg` powers the runtime `AsyncEngine`; `psycopg2-binary` is only there because alembic can't do async migrations.
- **Federation bundle in the same repo.** `frontend/vite.remote.config.ts` exposes `ConnectMyChart` / `MyChartCallback` / `MyChartConnections` / `ConnectHealthEx` / `HealthExConnections`. Dockerfile stage 1 (`FROM node`) builds them; stage 2 (`FROM python`) mounts `/app/frontend_remote` at `/remote` via `StaticFiles` in `app/main.py`. Host SPA loads `<service-url>/remote/remoteEntry.js`.
- **Sentry initialized before FastAPI app construction** (`app/main.py`) so import-time and lifespan errors are captured. `logger.exception(...)` auto-reports; INFO/WARNING become breadcrumbs. Empty `SENTRY_DSN` = SDK off.

## Common commands

```bash
# Backend
make pytest                                    # full test suite
python -m pytest tests/test_healthex_routes.py # single file
python -m pytest -k "ingest_incremental"       # single test by name
python -m pytest -x                            # stop on first failure

# Alembic (runtime env must be loaded)
set -a; source .env; set +a && alembic upgrade head
alembic revision --autogenerate -m "..."

# Local dev API — venv mode
uvicorn app.main:app --reload --port 8030

# Frontend federation remote (Vite dev server on :5178)
make ui              # dev
make ui-build        # produce dist/remote/ for the Docker image

# Smoke check against production
make smoke           # hits /remote/remoteEntry.js + /epic/organizations

# Deploy — rsyncs deploy/ to cancerbot-prod-app; CI push to main also triggers
make deploy
```

Local end-to-end (backend + emulators + host SPA) is documented in `LOCAL_DEV.md` — six terminals. Note the fixed **`http://localhost:3001`** for the host: it's what Epic's admin has registered as the redirect URI, and Firebase sessions are per-origin.

## Testing shape (follow this when adding tests)

- **Free functions, not classes.** `test_routes.py`, `test_service.py`, `test_healthex_routes.py` — no test classes. `test_state_store.py` has one and only because state transitions genuinely group.
- **`pytest-asyncio` in auto mode** (per `pyproject.toml`) — write `async def test_...` freely; no `@pytest.mark.asyncio` needed.
- **Scoped app fixtures.** Don't extend the conftest Epic `app` fixture for a new router — build a small `FastAPI()` in the test module that mounts only the router you're testing. Prevents dep changes on one router from silently breaking the other's tests. See `tests/test_healthex_routes.py:healthex_app`.
- **`create_autospec` for external clients** (`HealthExClient`, `BaseAirflowClient`). Prefer over hand-written fakes for anything where signature drift matters more than behaviour. Hand-written fakes (`InMemoryConnectionsRepository`, `InMemoryHealthExLinksRepository`) for repositories — the test needs realistic CRUD behaviour, autospec doesn't give you that.
- **Bearer token fixture: `{"Authorization": "Bearer test-token"}`** matched by `StaticTokenVerifier` in `tests/fakes.py` — use it for authed requests.

## Deploy topology

Production runs `docker compose` on a single host (`cancerbot-prod-app`) using `deploy/docker-compose.yaml`. The compose file on the host is out-of-band (not synced from repo — `make deploy` rsyncs the `deploy/` directory). CI workflow `.github/workflows/deploy.yml` SSHes in, pulls the AR image tagged `$GITHUB_SHA`, runs `docker compose run --rm -T app alembic upgrade head </dev/null`, then `docker compose up -d --force-recreate` with a 30s health-poll gate.

Env vars flow: `.env` on the host → compose `env_file` → container. Certain ones (`FIREBASE_PROJECT_ID`, `SENTRY_*`, `DATABASE_URL`, `HEALTHEX_*`, etc.) also need to be listed by name in the compose `environment:` block for compose to actually pass them through. When adding a new env var, update both `.env` (or documentation) AND `deploy/docker-compose.yaml`.

## Code style (from `CODESTYLE.md`)

- **No file-level or package-level comments.**
- **Class docstrings** state purpose, responsibility, boundaries.
- **Method docstrings** are one-liners when they help; skip when the name is self-evident.
- **Comments explain WHY**, not WHAT. Non-obvious tradeoffs, historical incidents, upstream quirks. If a comment describes what the code does, rename identifiers instead.
- **Line length: 120** (pylint config). **mypy strict** — all defs typed, no `Any` in return types.

## Docs worth reading

- `docs/DATA_FLOW.md` — cross-service data flow with SHALL/MUST contracts. Treat as Definition of Done.
- `docs/healthex-integration.md` — HealthEx API quirks, live-verified endpoints, sandbox status, contact.
- `docs/healthkey-etl-integration.md` — Airflow DAG interface (conf schema, DAG names).
- `docs/frontend-remote.md` — what the host SPA sees when consuming the federation bundle.
- `docs/token-management.md` — Epic OAuth token refresh + Fernet encryption design.
- `docs/observability.md` — logging conventions + Sentry.
- `LOCAL_DEV.md` — six-terminal local setup.
- `deploy/README.md` (if present) or `docs/deployment.md` — host-side ops.


## Testing

`pytest.ini` defines decorators for test categorization:

Unit tests:
No special marker
Run with `make pytest_unit`
Must have zero external dependencies (no DB, no LLM calls, etc), be fast and cheap to run.

Fresh database tests:
Marked with `@pytest.mark.db_fresh`
Run with `make pytest_db_fresh`
Wipes database before each individual test, ensuring a clean state.
Useful for detailed testing (when created 1 trial, then assert DB has exactly 1 trial, etc).

Seeded database tests:
Marked with `@pytest.mark.db_seeded`
Run with `make pytest_db_seeded`
Restores fresh database backup before test batch
All tests must be read-only
Useful for data integrity testing (fetch 1000 trials, assert all 1000 trials have compatible enum values, etc)
Use `pytest_db_seeded_prepare` to recreate the seeded database (need only once if it was destroyed/modified)

So, your checklist:
```bash
make pytest_unit
make pytest_db_fresh
make pytest_db_seeded_prepare
make pytest_db_seeded
```