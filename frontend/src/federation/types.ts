import type { AxiosInstance } from "axios";

export interface Organization {
  alias: string;
  title: string;
  endpoint_url: string;
}

export interface FinishResult {
  /** Persisted connection id (tokens are stored server-side, never returned). */
  connection_id: number;
  /** Sync job kicked off for this connection — poll GET /epic/sync/{id}. */
  sync_job_id: number;
  organization_alias: string;
  expires_in: number;
  scope: string | null;
  patient: string | null;
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

export interface ConnectMyChartProps extends MyChartBaseProps {
  /** Called if loading organizations or starting the auth flow fails. */
  onError?: (error: Error) => void;
  /** Org aliases to hide from the picker (e.g. already-connected hospitals). */
  excludeAliases?: string[];
}

export interface MyChartCallbackProps extends MyChartBaseProps {
  /** OAuth authorization code. Falls back to `?code=` in the current URL. */
  code?: string;
  /** OAuth state. Falls back to `?state=` in the current URL. */
  state?: string;
  /** Called once tokens are successfully retrieved from /epic/auth/finish. */
  onSuccess?: (result: FinishResult) => void;
  /** Called if the token exchange fails. */
  onError?: (error: Error) => void;
}
