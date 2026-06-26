import dns from "node:dns";
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { federation } from "@module-federation/vite";

// Resolve localhost to 127.0.0.1 (IPv4) first, and bind explicitly to IPv4 so
// the remote is reachable at 127.0.0.1:5178 (matches how the host is served).
dns.setDefaultResultOrder("ipv4first");

// Federation remote build. Exposes the MyChart components as a Module
// Federation 2.0 remote. The microservice URL is baked in from VITE_API_BASE_URL
// at build time (see src/federation/config.ts) — the host does not configure it.
export default defineConfig({
  plugins: [
    react(),
    federation({
      name: "mychart_remote",
      filename: "remoteEntry.js",
      exposes: {
        "./ConnectMyChart": "./src/federation/ConnectMyChart.tsx",
        "./MyChartCallback": "./src/federation/MyChartCallback.tsx",
        "./MyChartConnections": "./src/federation/MyChartConnections.tsx",
        "./ConnectHealthEx": "./src/federation/ConnectHealthEx.tsx",
        "./HealthExConnections": "./src/federation/HealthExConnections.tsx",
        "./types": "./src/federation/types.ts",
      },
      shared: {
        react: { singleton: true, strictVersion: false },
        "react-dom": { singleton: true, strictVersion: false },
        "react/jsx-runtime": { singleton: true, strictVersion: false },
        "react/jsx-dev-runtime": { singleton: true, strictVersion: false },
        axios: { singleton: true, strictVersion: false },
      },
      dts: false,
    }),
  ],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  cacheDir: "node_modules/.vite-remote",
  build: {
    outDir: "dist/remote",
    target: "esnext",
  },
  server: {
    host: "127.0.0.1",
    port: 5178,
    strictPort: true,
  },
});
