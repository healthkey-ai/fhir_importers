import { createContext, useContext, useMemo } from "react";
import type { AxiosInstance } from "axios";
import { createMyChartClient, type MyChartClient } from "./client";

interface MyChartContextValue {
  apiClient: AxiosInstance;
  apiBasePath: string;
}

const MyChartContext = createContext<MyChartContextValue | null>(null);

// eslint-disable-next-line react-refresh/only-export-components
export function useMyChartClient(): MyChartClient {
  const ctx = useContext(MyChartContext);
  if (!ctx) {
    throw new Error("useMyChartClient must be used inside <MyChartProvider>");
  }
  return useMemo(
    () => createMyChartClient(ctx.apiClient, ctx.apiBasePath),
    [ctx.apiClient, ctx.apiBasePath],
  );
}

export { MyChartContext };
