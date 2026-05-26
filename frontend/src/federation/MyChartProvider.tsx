import { type ReactNode } from "react";
import { MyChartContext } from "./MyChartContext";
import { injectStyles } from "./injectStyles";
import { DEFAULT_API_BASE_URL } from "./config";

// Inject scoped styles once at module load.
injectStyles();

interface MyChartProviderProps {
  apiBaseUrl?: string;
  className?: string;
  children: ReactNode;
}

export function MyChartProvider({ apiBaseUrl, className, children }: MyChartProviderProps) {
  const baseUrl = apiBaseUrl ?? DEFAULT_API_BASE_URL;
  return (
    <MyChartContext.Provider value={{ apiBaseUrl: baseUrl }}>
      <div className={`mychart-root ${className ?? ""}`.trim()}>{children}</div>
    </MyChartContext.Provider>
  );
}
