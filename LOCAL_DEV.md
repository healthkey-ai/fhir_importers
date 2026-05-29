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
| MyChart microservice (FastAPI + Redis, Docker) | http://127.0.0.1:8030 |
| MyChart federated remote (Vite) | http://127.0.0.1:5178 |
| Firebase Auth emulator | http://127.0.0.1:9099 |
| ht-phr backend (Django) | http://127.0.0.1:8000 |
| ht-phr frontend / host (Vite) | **http://localhost:3001** |

All commands below start from the repo root (`fhir-importers/`).

---

## First-time setup (once)

```bash
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

## Run (5 terminal tabs)

### Tab 1 — MyChart microservice + Redis (:8030)

```bash
docker compose up -d
```

### Tab 2 — MyChart federated remote (:5178)

```bash
cd frontend
npm run dev:remote
```

### Tab 3 — Firebase Auth emulator (:9099)

```bash
cd examples/ht-phr
npx -y firebase-tools emulators:start --only auth --project demo-ht-phr
```

### Tab 4 — ht-phr backend (:8000)

```bash
cd examples/ht-phr/backend
source .venv/bin/activate
python manage.py runserver
```

(`backend/.env` already sets `FIREBASE_AUTH_EMULATOR_HOST` + `FIREBASE_PROJECT_ID`.)

### Tab 5 — ht-phr frontend / host (:3001)

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

- **Restart Tab 5 after editing `examples/ht-phr/frontend/.env`** — Vite reads env
  + the federation config only at startup.
- **Editing the root `.env`** (microservice config / CORS) needs `docker compose up -d`
  again to recreate the container (`restart` won't re-read it).
- **Two Epic configs**: the `my_chart_central` sandbox org uses the **staging**
  Epic app (`STAGING_*` in root `.env`, redirect `http://localhost:3001/redirections/epic`);
  every real org uses the **production** app (`PROD_*`). Only the sandbox flow is
  testable locally — fill in `PROD_*` to use real hospitals.
- **Epic redirect**: the staging redirect (`http://localhost:3001/redirections/epic`)
  must be registered with the Epic sandbox client (your admin did this). It's
  handled by the host's public `/redirections/epic` route.
- Stop the microservice: `docker compose down`. Stop the others with Ctrl-C.
