import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConnectMyChart } from "./federation/ConnectMyChart";
import { MyChartCallback } from "./federation/MyChartCallback";

// Standalone dev harness. Mounts the federated components directly (no router),
// the same way a host app does. Visit `/` for ConnectMyChart and
// `/after-auth-epic` (where Epic redirects) for MyChartCallback.
function DevHarness() {
  const path = window.location.pathname;
  if (path === "/after-auth-epic") {
    return (
      <MyChartCallback
        onSuccess={(r) => console.log("[harness] onSuccess", r)}
        onError={(e) => console.error("[harness] onError", e)}
      />
    );
  }
  return <ConnectMyChart onError={(e) => console.error("[harness] onError", e)} />;
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
