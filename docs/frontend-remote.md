# Frontend remote (Module Federation)

**This document is the source of truth for the ht-phr ↔ fhir-importers federation contract** — exposed components, shared singletons, host obligations — plus the build details on this side.

fhir-importers SHALL expose a Module Federation 2.0 remote at `<connector-origin>/remote/remoteEntry.js`.

## Exposed components

| Specifier | Purpose |
|---|---|
| `mychart_remote/ConnectMyChart` | Org picker + Connect button; initiates OAuth |
| `mychart_remote/MyChartCallback` | Handles the redirect URI; calls `/auth/finish` |
| `mychart_remote/MyChartConnections` | Lists + manages connections |
| `mychart_remote/types` | Shared TypeScript types |

## Shared singletons required by the host

`react`, `react-dom`, `react/jsx-runtime`, `react/jsx-dev-runtime`, `axios`.

## Host obligations (SHALL)

- Configure the remote in its MF host config under name `mychart_remote`.
- Pass an authenticated `axios` instance (with `Authorization: Bearer <user JWT>`) and an `apiBasePath` prop to every component.
- Host the Epic-registered redirect URI route and render `MyChartCallback` there.

**Host SHALL NOT** talk to Epic directly, persist Epic tokens, or resolve OAuth `state` itself.

**Host build-time env**: `VITE_MYCHART_REMOTE_URL`, `VITE_FHIR_IMPORTER_URL`.

## Build (this side)

Vite + `@module-federation/vite`. The frontend builds into `frontend/dist/`; FastAPI serves it as a static mount at `/remote`. The Dockerfile is multi-stage:

1. **Node stage**: `npm ci` + `npm run build:remote` → produces `frontend/dist/` containing `remoteEntry.js` + chunks.
2. **Python stage**: copies the built `frontend/dist/` into the runtime image alongside the FastAPI app.

If `frontend/dist/` is missing at startup (e.g. uvicorn invoked outside the image without `npm run build:remote`), the `/remote` mount is skipped — `/health` and the JSON API still respond.

## Local dev

The federation remote and the FastAPI backend run as separate processes (Vite dev server + FastAPI on `:8030`). Production serves both from a single container.

`.mjs` requires an explicit MIME type when served as a static file; the FastAPI app calls `mimetypes.add_type("application/javascript", ".mjs")` at import time.

## CORS

`CORSMiddleware` is configured from the `CORS_ALLOWED_ORIGINS` env var (comma-separated). It applies to both the JSON API and the `/remote` mount, so the host SPA can fetch the remote entry from a different origin.
