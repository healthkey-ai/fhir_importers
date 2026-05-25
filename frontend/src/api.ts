import { API_BASE_URL } from "./config";

export interface Organization {
  alias: string;
  title: string;
  endpoint_url: string;
}

export interface StartResponse {
  authorization_url: string;
  state: string;
}

export interface FinishResponse {
  access_token: string;
  refresh_token: string | null;
  id_token: string | null;
  expires_in: number;
  scope: string | null;
  patient: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      // body wasn't JSON; keep statusText
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listOrganizations: () => request<Organization[]>("/epic/organizations"),
  start: (organization_alias: string) =>
    request<StartResponse>("/epic/auth/start", {
      method: "POST",
      body: JSON.stringify({ organization_alias }),
    }),
  finish: (code: string, state: string) =>
    request<FinishResponse>("/epic/auth/finish", {
      method: "POST",
      body: JSON.stringify({ code, state }),
    }),
};
