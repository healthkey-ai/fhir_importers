# MyChart Federation Module

Exposes `<ConnectMyChart />` and `<MyChartCallback />` as Module Federation 2.0
remote components (`@module-federation/vite`). The host embeds the connect widget
and renders the callback component on its own OAuth redirect route.

## Remote Entry

- Build: `npm run build:remote` → `dist/remote/remoteEntry.js`
- Dev: `npm run dev:remote` → serves the remote on `:5175`
- Standalone harness: `npm run dev` → `:5173` (mounts both components by path)

The microservice URL is **owned by this module**, not the host. It is inlined
from `VITE_API_BASE_URL` at remote-build time (`src/federation/config.ts`). Build
the remote with the correct value per environment, e.g.:

```bash
VITE_API_BASE_URL=https://app.cancerbot.org:8030 npm run build:remote
```

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

// On the "connect your records" page:
<Suspense fallback={<Spinner />}>
  <ConnectMyChart onError={(e) => toast.error(e.message)} />
</Suspense>

// On the OAuth redirect route (see below):
<Suspense fallback={<Spinner />}>
  <MyChartCallback
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
| `apiBaseUrl` | `string` | Optional override of the baked-in microservice URL |
| `className` | `string` | Extra class on the `.mychart-root` container |
| `onError` | `(error: Error) => void` | Loading orgs / starting auth failed |

### `<MyChartCallback />`

| Prop | Type | Description |
|------|------|-------------|
| `apiBaseUrl` | `string` | Optional override of the baked-in microservice URL |
| `className` | `string` | Extra class on the `.mychart-root` container |
| `code` | `string` | Optional; falls back to `?code=` in the URL |
| `state` | `string` | Optional; falls back to `?state=` in the URL |
| `onSuccess` | `(result: FinishResult) => void` | Tokens retrieved from `/epic/auth/finish` |
| `onError` | `(error: Error) => void` | Token exchange failed |

## Shared dependencies (singletons)

`react`, `react-dom`, `react/jsx-runtime`, `react/jsx-dev-runtime`. The host must
provide React 18/19; `strictVersion` is off so minor drift is tolerated. This
module brings its own fetch client and styles (scoped under `.mychart-root`,
injected once) — no axios/react-query/CSS framework required from the host.
