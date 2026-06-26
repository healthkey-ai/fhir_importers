import { createContext, useContext, useMemo } from "react";
import type { AxiosInstance } from "axios";
import { createHealthExClient, type HealthExClient } from "./healthexClient";

interface HealthExContextValue {
  apiClient: AxiosInstance;
  apiBasePath: string;
}

const HealthExContext = createContext<HealthExContextValue | null>(null);

// eslint-disable-next-line react-refresh/only-export-components
export function useHealthExClient(): HealthExClient {
  const ctx = useContext(HealthExContext);
  if (!ctx) {
    throw new Error("useHealthExClient must be used inside <HealthExProvider>");
  }
  return useMemo(
    () => createHealthExClient(ctx.apiClient, ctx.apiBasePath),
    [ctx.apiClient, ctx.apiBasePath],
  );
}

export { HealthExContext };
