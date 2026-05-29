import { useCallback, useEffect, useState } from "react";
import { MyChartProvider } from "./MyChartProvider";
import { useMyChartClient } from "./MyChartContext";
import type { Connection, MyChartConnectionsProps } from "./types";

function MyChartConnectionsInner({ onError }: Pick<MyChartConnectionsProps, "onError">) {
  const client = useMyChartClient();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [conns, orgs] = await Promise.all([
        client.listConnections(),
        client.listOrganizations(),
      ]);
      setConnections(conns);
      setTitles(Object.fromEntries(orgs.map((o) => [o.alias, o.title])));
    } catch (e: unknown) {
      const err = e instanceof Error ? e : new Error(String(e));
      setError(err.message);
      onError?.(err);
    } finally {
      setLoading(false);
    }
  }, [client, onError]);

  useEffect(() => {
    load();
  }, [load]);

  const disconnect = async (alias: string) => {
    setDeleting(alias);
    setError(null);
    try {
      await client.deleteConnection(alias);
      setConnections((prev) => prev.filter((c) => c.organization_alias !== alias));
    } catch (e: unknown) {
      const err = e instanceof Error ? e : new Error(String(e));
      setError(err.message);
      onError?.(err);
    } finally {
      setDeleting(null);
    }
  };

  return (
    <>
      <h2>Connected records</h2>

      {loading && <p>Loading connections…</p>}
      {error && <div className="mychart-error">{error}</div>}

      {!loading && !error && connections.length === 0 && (
        <p className="mychart-muted">No connected MyChart accounts yet.</p>
      )}

      {connections.length > 0 && (
        <ul className="mychart-connection-list">
          {connections.map((c) => (
            <li key={c.organization_alias} className="mychart-connection">
              <div>
                <div className="mychart-connection-title">
                  {titles[c.organization_alias] ?? c.organization_alias}
                </div>
                <div className="mychart-connection-meta">
                  {c.patient ? `Patient ${c.patient} · ` : ""}
                  connected {new Date(c.connected_at).toLocaleDateString()}
                </div>
              </div>
              <button
                type="button"
                className="mychart-disconnect"
                onClick={() => disconnect(c.organization_alias)}
                disabled={deleting === c.organization_alias}
              >
                {deleting === c.organization_alias ? "Removing…" : "Disconnect"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function MyChartConnections({ apiClient, apiBasePath, className, onError }: MyChartConnectionsProps) {
  return (
    <MyChartProvider apiClient={apiClient} apiBasePath={apiBasePath} className={className}>
      <MyChartConnectionsInner onError={onError} />
    </MyChartProvider>
  );
}

export default MyChartConnections;
