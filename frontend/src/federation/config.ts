// The MyChart microservice URL is owned by this module, not the host app.
// It is inlined at remote-build time from VITE_API_BASE_URL; build the remote
// with the right value for each environment. The host never configures it.
export const DEFAULT_API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8765";
