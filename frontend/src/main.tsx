import { StrictMode, useMemo } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import { ConnectMyChart } from "./federation/ConnectMyChart";
import { MyChartCallback } from "./federation/MyChartCallback";

// Standalone dev harness. It plays the role of the HOST: it constructs the
// (optionally authenticated) axios client and injects it, the same way ht-phr
// does via useMyChartApi(). Visit `/` for ConnectMyChart and `/after-auth-epic`
// (where Epic redirects) for MyChartCallback.
function DevHarness() {
  const apiClient = useMemo(() => {
    const client = axios.create({
      baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:9300",
    });
    // Dev convenience: attach a token if one was stashed for local testing.
    const token = localStorage.getItem("dev_token");
    if (token) client.defaults.headers.common.Authorization = `Bearer ${token}`;
    return client;
  }, []);

  const path = window.location.pathname;
  if (path === "/after-auth-epic") {
    return (
      <MyChartCallback
        apiClient={apiClient}
        onSuccess={(r) =>
          console.log("[harness] onSuccess", {
            patient: r.patient,
            scope: r.scope,
            expires_in: r.expires_in,
          })
        }
        onError={(e) => console.error("[harness] onError", e.message)}
      />
    );
  }
  return (
    <ConnectMyChart
      apiClient={apiClient}
      onError={(e) => console.error("[harness] onError", e.message)}
    />
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <div
      style={{
        maxWidth: 640,
        margin: "3rem auto",
        padding: "2rem",
        background: "white",
        borderRadius: 12,
        boxShadow: "0 4px 12px rgba(0,0,0,0.06)",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      <h1>MyChart Federation — Dev Harness</h1>
      <DevHarness />
    </div>
  </StrictMode>,
);
