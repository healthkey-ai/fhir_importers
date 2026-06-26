# Running everything locally

End-to-end local setup for the MyChart microservice + its federated frontend,
consumed by the ht-phr host app.

> Open the **host at `http://localhost:3001`** — that exact host:port is what your
> admin registered with Epic as the redirect (`/redirections/epic`), and Firebase
> sessions are per-origin. The remote and microservice are reached at `127.0.0.1`
> (CORS allows the `localhost:3001` origin).

## Ports

| What | URL |
|------|-----|
| fhir-importers microservice (FastAPI, venv) | http://127.0.0.1:8030 |
| Postgres (Docker) — host port | 127.0.0.1:**55432** |
| Redis (Docker) | 127.0.0.1:6379 |
| Federated remote (Vite) | http://127.0.0.1:5178 |
| Firebase Auth emulator | http://127.0.0.1:9099 |
| ht-phr backend (Django) | http://127.0.0.1:8000 |
| ht-phr frontend / host (Vite) | **http://localhost:3001** |

> The microservice runs FastAPI from the host venv (hot reload), with postgres + redis in Docker. The compose file's `app` service is the prod-shaped path (full container build) and isn't needed for day-to-day dev.
>
> Postgres is published on host port `:55432` (not `:5432`) via `docker-compose.override.yml` to avoid colliding with any other postgres on the dev box. Set `DATABASE_URL` in `.env` accordingly:
>
> ```
> DATABASE_URL=postgresql+asyncpg://fhir:fhir_dev_only@localhost:55432/fhir_importers
> ```

All commands below start from the repo root (`fhir-importers/`).

---

## First-time setup (once)

```bash
# fhir-importers backend (this repo)
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
deactivate

# microservice frontend (the federated remote)
cd frontend && npm install && cd ..

# ht-phr frontend (the host)
cd examples/ht-phr/frontend && npm install && cd ../../..

# ht-phr backend
cd examples/ht-phr/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
cd ../../..
```

---

## Run (6 terminal tabs)

### Tab 1 — Infra: postgres + redis (Docker, background)

```bash
docker compose up -d postgres redis
```

Ephemeral by design — postgres has no volume mount, so every `up` is a fresh DB. Tab 2 reapplies migrations on each boot.

### Tab 2 — fhir-importers backend (:8030, venv)

```bash
set -a; source .env; set +a            # exports DATABASE_URL etc. from .env
venv/bin/alembic upgrade head          # required after every fresh postgres boot
venv/bin/uvicorn app.main:app --port 8030 --reload
```

> If sourcing prints `bash: profile: command not found`, you have unquoted whitespace in `.env`. Quote the values of `STAGING_SCOPES` and `PROD_SCOPES` (and anything else with spaces).

### Tab 3 — Federated remote (:5178)

```bash
cd frontend
npm run dev:remote
```

### Tab 4 — Firebase Auth emulator (:9099)

```bash
cd examples/ht-phr
npx -y firebase-tools emulators:start --only auth --project demo-ht-phr
```

### Tab 5 — ht-phr backend (:8000)

```bash
cd examples/ht-phr/backend
source .venv/bin/activate
python manage.py runserver
```

(`backend/.env` already sets `FIREBASE_AUTH_EMULATOR_HOST` + `FIREBASE_PROJECT_ID`.)

### Tab 6 — ht-phr frontend / host (:3001)

```bash
cd examples/ht-phr/frontend
npm run dev
```

---

## Use it

1. Open **http://localhost:3001**
2. Register / sign in (the Auth emulator accepts any email + password you enter).
3. Go to **Connect Records** in the sidebar → the MyChart hospital picker loads
   (≈476 orgs) from the federated remote.
4. Pick **MyChart Central** (the sandbox org) and Connect → Epic → it redirects
   back to `http://localhost:3001/redirections/epic`, which exchanges the code.

## Notes

- **Restart Tab 6 after editing `examples/ht-phr/frontend/.env`** — Vite reads env
  + the federation config only at startup.
- **Restart Tab 2 after editing the root `.env`** — uvicorn captures env at process
  start; `--reload` watches `.py` changes only, not env.
- **Re-run `alembic upgrade head` (Tab 2) after every `docker compose down`** —
  postgres is ephemeral. If you see `column X does not exist`, that's the tell.
- **Two Epic configs**: the `my_chart_central` sandbox org uses the **staging**
  Epic app (`STAGING_*` in root `.env`, redirect `http://localhost:3001/redirections/epic`);
  every real org uses the **production** app (`PROD_*`). Only the sandbox flow is
  testable locally — fill in `PROD_*` to use real hospitals.
- **Epic redirect**: the staging redirect (`http://localhost:3001/redirections/epic`)
  must be registered with the Epic sandbox client (your admin did this). It's
  handled by the host's public `/redirections/epic` route.
- **HealthEx redirect**: a separate flow — patient consents at `app.healthex.io`
  and HealthEx redirects back to the URL in the admin-side "Redirect URLs"
  whitelist. Must include the exact origin + path the `<ConnectHealthEx>` host
  page lands on (e.g. `http://localhost:3001/connect/records`).
- Stop infra: `docker compose down`. Stop the others with Ctrl-C.
