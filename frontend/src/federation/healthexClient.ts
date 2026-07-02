import type { AxiosInstance } from "axios";
import type {
  HealthExIngestResult,
  HealthExLink,
  HealthExReconcileResult,
  HealthExStatusResult,
} from "./types";

export interface HealthExClient {
  connect: (
    email: string,
    firstName?: string,
    lastName?: string,
    redirectUri?: string,
  ) => Promise<HealthExLink>;
  listConnections: () => Promise<HealthExLink[]>;
  getStatus: (projectId: string) => Promise<HealthExStatusResult>;
  ingest: (projectId: string) => Promise<HealthExIngestResult>;
  reconcile: (projectId: string) => Promise<HealthExReconcileResult>;
  deleteConnection: (projectId: string) => Promise<void>;
}

// Pull a FastAPI `{ "detail": ... }` message out of an axios error.
function detail(e: unknown): string {
  const err = e as { response?: { data?: { detail?: unknown } }; message?: string };
  const d = err?.response?.data?.detail;
  if (d) return String(d);
  return err?.message ?? String(e);
}

export function createHealthExClient(
  apiClient: AxiosInstance,
  apiBasePath = "",
): HealthExClient {
  const base = apiBasePath.replace(/\/+$/, "");

  async function get<T>(path: string): Promise<T> {
    try {
      const res = await apiClient.get<T>(`${base}${path}`);
      return res.data;
    } catch (e) {
      throw new Error(detail(e));
    }
  }

  async function post<T>(path: string, body: unknown): Promise<T> {
    try {
      const res = await apiClient.post<T>(`${base}${path}`, body);
      return res.data;
    } catch (e) {
      throw new Error(detail(e));
    }
  }

  async function del(path: string): Promise<void> {
    try {
      await apiClient.delete(`${base}${path}`);
    } catch (e) {
      throw new Error(detail(e));
    }
  }

  return {
    connect: (email, firstName, lastName, redirectUri) =>
      post<HealthExLink>("/healthex/connect", {
        email,
        first_name: firstName,
        last_name: lastName,
        redirect_uri: redirectUri,
      }),
    listConnections: () => get<HealthExLink[]>("/healthex/connections"),
    getStatus: (projectId) =>
      get<HealthExStatusResult>(
        `/healthex/connections/${encodeURIComponent(projectId)}/status`,
      ),
    ingest: (projectId) =>
      post<HealthExIngestResult>(
        `/healthex/connections/${encodeURIComponent(projectId)}/ingest`,
        {},
      ),
    reconcile: (projectId) =>
      post<HealthExReconcileResult>(
        `/healthex/connections/${encodeURIComponent(projectId)}/reconcile`,
        {},
      ),
    deleteConnection: (projectId) =>
      del(`/healthex/connections/${encodeURIComponent(projectId)}`),
  };
}
