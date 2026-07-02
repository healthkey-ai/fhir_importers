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

// =============================================================================
// HealthEx
// =============================================================================

export type HealthExStatus =
  | "PENDING_CONSENT"
  | "RETRIEVAL_IN_PROGRESS"
  | "COMPLETE"
  | "ERROR"
  | "REVOKED";

export interface HealthExLink {
  project_id: string;
  external_id: string;
  healthex_patient_id: string | null;
  status: HealthExStatus;
  onboarding_url: string | null;
  consented_at: string | null;
  last_status_polled_at: string | null;
  last_synced_at: string | null;
  connected_at: string;
}

export interface HealthExStatusResult {
  project_id: string;
  healthex_patient_id: string | null;
  status: HealthExStatus;
  overall_status?: string | null;
  vectorization_status?: string | null;
  polled_at?: string | null;
}

/** Response for POST /healthex/connections/{project_id}/ingest.
 *
 * Fires the healthex_extract Airflow DAG; returns 202 with the dag_run_id.
 * Poll Airflow (or a future webhook) for completion.
 */
export interface HealthExIngestResult {
  project_id: string;
  dag_run_id: string;
}

/** Response for POST /healthex/connections/{project_id}/reconcile.
 *
 * Fires the healthex_reconcile Airflow DAG for a single row. Same shape as
 * HealthExIngestResult but a distinct type mirrors the backend split.
 */
export interface HealthExReconcileResult {
  project_id: string;
  dag_run_id: string;
}


export interface HealthExBaseProps {
  /** Authenticated HTTP client for the fhir-importers microservice. */
  apiClient: AxiosInstance;
  /** Optional path prefix in front of microservice routes. Default: "". */
  apiBasePath?: string;
  /** Extra class applied to the module's root container. */
  className?: string;
}

export interface ConnectHealthExProps extends HealthExBaseProps {
  /**
   * User's email — required by HealthEx's addPatients. The host has it from
   * its auth context; we don't make a separate request to fetch it.
   */
  email: string;
  firstName?: string;
  lastName?: string;
  /**
   * Where HealthEx should redirect the browser after consent.
   *
   * Passed to the fhir-importers `/healthex/connect` endpoint verbatim;
   * the backend attaches it to the HealthEx onboarding URL using whatever
   * encoding HealthEx expects. Consumers don't need to know the query-param
   * name or construction rules — just tell us the URI you want the user
   * to land on. Must EXACTLY match a URL registered in the HealthEx
   * project's "Redirect URLs" admin allowlist.
   */
  redirectUri?: string;
  /** Called once the patient has consented and patient_id is resolved. */
  onConnected?: (link: HealthExLink) => void;
  /** Called if connect or status polling fails. */
  onError?: (error: Error) => void;
}

export interface HealthExConnectionsProps extends HealthExBaseProps {
  /** Called if listing or deleting connections fails. */
  onError?: (error: Error) => void;
}
