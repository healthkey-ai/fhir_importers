# MyChart Federation Module

Exposes `<ConnectMyChart />` and `<MyChartCallback />` as Module Federation 2.0
remote components (`@module-federation/vite`). The host embeds the connect widget
and renders the callback component on its own OAuth redirect route.

## Remote Entry

- Build: `npm run build:remote` → `dist/remote/remoteEntry.js`
- Dev: `npm run dev:remote` → serves the remote on `:5178`
- Standalone harness: `npm run dev` → `:5173` (mounts both components by path)

The host injects an authenticated `apiClient` (axios). The host owns the
microservice base URL and auth — it attaches the user's bearer token via an
interceptor, exactly like ht-phr's `useLabsApi` / `usePhrApi`. This module never
sees credentials or the URL directly.

## Host integration (ht-phr)

```ts
// vite.config.ts — add to the host's federation() remotes:
mychart_remote: {
  type: "module",
  name: "mychart_remote",
  entry: `${mychartRemoteUrl}/remoteEntry.js`,
},
```

```tsx
import { lazy, Suspense } from "react";

const ConnectMyChart = lazy(() => import("mychart_remote/ConnectMyChart"));
const MyChartCallback = lazy(() => import("mychart_remote/MyChartCallback"));

// Build an authenticated client pointed at the MyChart microservice
// (host-owned URL + token), e.g. a useMyChartApi() hook:
const apiClient = useMyChartApi();

// On the "connect your records" page:
<Suspense fallback={<Spinner />}>
  <ConnectMyChart apiClient={apiClient} onError={(e) => toast.error(e.message)} />
</Suspense>

// On the OAuth redirect route (see below):
<Suspense fallback={<Spinner />}>
  <MyChartCallback
    apiClient={apiClient}
    onSuccess={(tokens) => saveEpicTokens(tokens)}
    onError={(e) => toast.error(e.message)}
  />
</Suspense>
```

## OAuth redirect routing (important)

Unlike a pure data widget, this flow leaves the SPA: `ConnectMyChart` redirects
the browser to Epic, and Epic redirects back to a fixed URL. In the federated
setup that URL is **host-owned**, so the host must:

1. Add a route (e.g. `/connect/mychart/callback`) that renders `<MyChartCallback />`.
2. Register that exact URL with the Epic client (`client_id`).
3. Set the microservice's `REDIRECT_URI` env to that same URL.

`MyChartCallback` reads `?code` and `?state` from `window.location.search` by
default; pass `code`/`state` props if your router consumes them first.

## Props

### `<ConnectMyChart />`

| Prop | Type | Description |
|------|------|-------------|
| `apiClient` | `AxiosInstance` | **Required.** Authenticated client for the microservice (host-owned URL + token) |
| `apiBasePath` | `string` | Optional path prefix in front of `/epic/*`. Default `""` |
| `className` | `string` | Extra class on the `.mychart-root` container |
| `onError` | `(error: Error) => void` | Loading orgs / starting auth failed |

### `<MyChartCallback />`

| Prop | Type | Description |
|------|------|-------------|
| `apiClient` | `AxiosInstance` | **Required.** Authenticated client for the microservice |
| `apiBasePath` | `string` | Optional path prefix. Default `""` |
| `className` | `string` | Extra class on the `.mychart-root` container |
| `code` | `string` | Optional; falls back to `?code=` in the URL |
| `state` | `string` | Optional; falls back to `?state=` in the URL |
| `onSuccess` | `(result: FinishResult) => void` | Tokens retrieved from `/epic/auth/finish` |
| `onError` | `(error: Error) => void` | Token exchange failed |

## Shared dependencies (singletons)

`react`, `react-dom`, `react/jsx-runtime`, `react/jsx-dev-runtime`, `axios`. The
host must provide React 18/19 and an axios instance; `strictVersion` is off so
minor drift is tolerated. Styles are scoped under `.mychart-root` and injected
once — no react-query/CSS framework required from the host.
