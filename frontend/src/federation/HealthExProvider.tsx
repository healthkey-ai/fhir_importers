import { type ReactNode } from "react";
import type { AxiosInstance } from "axios";
import { HealthExContext } from "./HealthExContext";
import { injectHealthExStyles } from "./injectHealthExStyles";

injectHealthExStyles();

interface HealthExProviderProps {
  apiClient: AxiosInstance;
  apiBasePath?: string;
  className?: string;
  children: ReactNode;
}

export function HealthExProvider({
  apiClient,
  apiBasePath = "",
  className,
  children,
}: HealthExProviderProps) {
  return (
    <HealthExContext.Provider value={{ apiClient, apiBasePath }}>
      <div className={`healthex-root ${className ?? ""}`.trim()}>{children}</div>
    </HealthExContext.Provider>
  );
}
