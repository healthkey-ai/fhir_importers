import type { AxiosInstance } from "axios";

export interface Organization {
  alias: string;
  title: string;
  endpoint_url: string;
}

// Returned by /epic/auth/finish. Tokens are persisted server-side and never
// returned to the browser — only this non-sensitive connection metadata.
export interface ConnectionResult {
  organization_alias: string;
  patient: string | null;
  scope: string | null;
  status: string;
  connected_at: string;
}

export interface MyChartBaseProps {
  /**
   * Authenticated HTTP client for the MyChart microservice, injected by the host.
   * The host owns the base URL and auth (e.g. attaches the user's bearer token).
   */
  apiClient: AxiosInstance;
  /** Optional path prefix in front of the microservice routes. Default: "". */
  apiBasePath?: string;
  /** Extra class applied to the module's root container. */
  className?: string;
}

export interface Connection {
  organization_alias: string;
  patient: string | null;
  scope: string | null;
  expires_at: string;
  connected_at: string;
}

export interface ConnectMyChartProps extends MyChartBaseProps {
  /** Called if loading organizations or starting the auth flow fails. */
  onError?: (error: Error) => void;
}

export interface MyChartConnectionsProps extends MyChartBaseProps {
  /** Called if listing or deleting connections fails. */
  onError?: (error: Error) => void;
}

export interface MyChartCallbackProps extends MyChartBaseProps {
  /** OAuth authorization code. Falls back to `?code=` in the current URL. */
  code?: string;
  /** OAuth state. Falls back to `?state=` in the current URL. */
  state?: string;
  /** Called once the connection is persisted by /epic/auth/finish. */
  onSuccess?: (result: ConnectionResult) => void;
  /** Called if the token exchange fails. */
  onError?: (error: Error) => void;
}
