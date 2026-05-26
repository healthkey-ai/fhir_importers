import { type ReactNode } from "react";
import type { AxiosInstance } from "axios";
import { MyChartContext } from "./MyChartContext";
import { injectStyles } from "./injectStyles";

// Inject scoped styles once at module load.
injectStyles();

interface MyChartProviderProps {
  apiClient: AxiosInstance;
  apiBasePath?: string;
  className?: string;
  children: ReactNode;
}

export function MyChartProvider({
  apiClient,
  apiBasePath = "",
  className,
  children,
}: MyChartProviderProps) {
  return (
    <MyChartContext.Provider value={{ apiClient, apiBasePath }}>
      <div className={`mychart-root ${className ?? ""}`.trim()}>{children}</div>
    </MyChartContext.Provider>
  );
}
