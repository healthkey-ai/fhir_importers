import type { AxiosInstance } from "axios";
import type { Connection, ConnectionResult, Organization } from "./types";

export interface MyChartClient {
  listOrganizations: () => Promise<Organization[]>;
  start: (organizationAlias: string) => Promise<{ authorization_url: string; state: string }>;
  finish: (code: string, state: string) => Promise<ConnectionResult>;
  listConnections: () => Promise<Connection[]>;
  deleteConnection: (organizationAlias: string) => Promise<void>;
}

// Pull a FastAPI `{ "detail": ... }` message out of an axios error without
// importing axios at runtime (we only depend on the host-provided instance).
function detail(e: unknown): string {
  const err = e as { response?: { data?: { detail?: unknown } }; message?: string };
  const d = err?.response?.data?.detail;
  if (d) return String(d);
  return err?.message ?? String(e);
}

export function createMyChartClient(apiClient: AxiosInstance, apiBasePath = ""): MyChartClient {
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
    listOrganizations: () => get<Organization[]>("/epic/organizations"),
    start: (organizationAlias: string) =>
      post<{ authorization_url: string; state: string }>("/epic/auth/start", {
        organization_alias: organizationAlias,
      }),
    finish: (code: string, state: string) =>
      post<ConnectionResult>("/epic/auth/finish", { code, state }),
    listConnections: () => get<Connection[]>("/epic/connections"),
    deleteConnection: (organizationAlias: string) =>
      del(`/epic/connections/${encodeURIComponent(organizationAlias)}`),
  };
}
