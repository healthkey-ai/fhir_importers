export interface Organization {
  alias: string;
  title: string;
  endpoint_url: string;
}

export interface FinishResult {
  access_token: string;
  refresh_token: string | null;
  id_token: string | null;
  expires_in: number;
  scope: string | null;
  patient: string | null;
}

export interface MyChartBaseProps {
  /**
   * Base URL of the MyChart microservice. Defaults to the value baked into this
   * module at build time (VITE_API_BASE_URL). The host normally does not set this.
   */
  apiBaseUrl?: string;
  /** Extra class applied to the module's root container. */
  className?: string;
}

export interface ConnectMyChartProps extends MyChartBaseProps {
  /** Called if loading organizations or starting the auth flow fails. */
  onError?: (error: Error) => void;
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
