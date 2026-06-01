import { useEffect, useState } from "react";
import { MyChartProvider } from "./MyChartProvider";
import { useMyChartClient } from "./MyChartContext";
import { OrganizationCombobox } from "./OrganizationCombobox";
import type { ConnectMyChartProps, Organization } from "./types";

function ConnectMyChartInner({
  onError,
  excludeAliases = [],
}: Pick<ConnectMyChartProps, "onError" | "excludeAliases">) {
  const client = useMyChartClient();
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selected, setSelected] = useState<Organization | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<boolean>(false);

  useEffect(() => {
    client
      .listOrganizations()
      .then((data) => setOrgs(data))
      .catch((e: unknown) => {
        const err = e instanceof Error ? e : new Error(String(e));
        setError(err.message);
        onError?.(err);
      })
      .finally(() => setLoading(false));
  }, [client, onError]);

  // Hide already-connected hospitals from the picker (they reappear once
  // disconnected, since the host passes the current connected aliases).
  const excluded = new Set(excludeAliases);
  const available = orgs.filter((o) => !excluded.has(o.alias));

  // If the selected org just got connected (excluded), drop it.
  useEffect(() => {
    if (selected && excluded.has(selected.alias)) setSelected(null);
  }, [selected, excludeAliases]); // eslint-disable-line react-hooks/exhaustive-deps

  const connect = async () => {
    if (!selected) return;
    setConnecting(true);
    setError(null);
    try {
      const { authorization_url } = await client.start(selected.alias);
      window.location.href = authorization_url;
    } catch (e: unknown) {
      const err = e instanceof Error ? e : new Error(String(e));
      setError(err.message);
      onError?.(err);
      setConnecting(false);
    }
  };

  return (
    <>
      {loading && <p>Loading organizations…</p>}
      {error && <div className="mychart-error">{error}</div>}

      {!loading && (
        <>
          <OrganizationCombobox
            organizations={available}
            value={selected}
            onChange={setSelected}
            disabled={connecting || available.length === 0}
            placeholder="Start typing a hospital name…"
          />
          {available.length === 0 && (
            <p className="mychart-muted">
              {orgs.length === 0
                ? "No hospitals are available to connect."
                : "You've connected all available hospitals."}
            </p>
          )}
          <button type="button" onClick={connect} disabled={!selected || connecting}>
            {connecting ? "Redirecting…" : selected ? `Connect ${selected.title}` : "Connect"}
          </button>
        </>
      )}
    </>
  );
}

export function ConnectMyChart({
  apiClient,
  apiBasePath,
  className,
  onError,
  excludeAliases,
}: ConnectMyChartProps) {
  return (
    <MyChartProvider apiClient={apiClient} apiBasePath={apiBasePath} className={className}>
      <ConnectMyChartInner onError={onError} excludeAliases={excludeAliases} />
    </MyChartProvider>
  );
}

export default ConnectMyChart;
