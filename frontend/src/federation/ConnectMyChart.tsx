import { useEffect, useState } from "react";
import { MyChartProvider } from "./MyChartProvider";
import { useMyChartClient } from "./MyChartContext";
import { OrganizationCombobox } from "./OrganizationCombobox";
import type { ConnectMyChartProps, Organization } from "./types";

function ConnectMyChartInner({ onError }: Pick<ConnectMyChartProps, "onError">) {
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
      <h2>Connect MyChart</h2>
      <p className="mychart-muted">
        Select your hospital and connect your MyChart account.
      </p>

      {loading && <p>Loading organizations…</p>}
      {error && <div className="mychart-error">{error}</div>}

      {!loading && (
        <>
          <label htmlFor="mychart-org">Hospital / organization</label>
          <OrganizationCombobox
            organizations={orgs}
            value={selected}
            onChange={setSelected}
            disabled={connecting || orgs.length === 0}
            placeholder="Start typing a hospital name…"
          />
          <button type="button" onClick={connect} disabled={!selected || connecting}>
            {connecting ? "Redirecting…" : "Connect MyChart"}
          </button>
        </>
      )}
    </>
  );
}

export function ConnectMyChart({ apiBaseUrl, className, onError }: ConnectMyChartProps) {
  return (
    <MyChartProvider apiBaseUrl={apiBaseUrl} className={className}>
      <ConnectMyChartInner onError={onError} />
    </MyChartProvider>
  );
}

export default ConnectMyChart;
