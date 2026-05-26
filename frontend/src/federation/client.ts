import type { FinishResult, Organization } from "./types";

export interface MyChartClient {
  listOrganizations: () => Promise<Organization[]>;
  start: (organizationAlias: string) => Promise<{ authorization_url: string; state: string }>;
  finish: (code: string, state: string) => Promise<FinishResult>;
}

export function createMyChartClient(baseUrl: string): MyChartClient {
  const root = baseUrl.replace(/\/+$/, "");

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${root}${path}`, {
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail ?? JSON.stringify(body);
      } catch {
        // non-JSON body; keep statusText
      }
      throw new Error(`${res.status} ${detail}`);
    }
    return res.json() as Promise<T>;
  }

  return {
    listOrganizations: () => request<Organization[]>("/epic/organizations"),
    start: (organizationAlias: string) =>
      request<{ authorization_url: string; state: string }>("/epic/auth/start", {
        method: "POST",
        body: JSON.stringify({ organization_alias: organizationAlias }),
      }),
    finish: (code: string, state: string) =>
      request<FinishResult>("/epic/auth/finish", {
        method: "POST",
        body: JSON.stringify({ code, state }),
      }),
  };
}
