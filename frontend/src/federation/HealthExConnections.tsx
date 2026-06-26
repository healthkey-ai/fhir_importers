import { useCallback, useEffect, useState } from "react";
import { HealthExProvider } from "./HealthExProvider";
import { useHealthExClient } from "./HealthExContext";
import type {
  HealthExConnectionsProps,
  HealthExLink,
  HealthExStatus,
} from "./types";

const BADGE_LABEL: Record<HealthExStatus, string> = {
  PENDING_CONSENT: "Pending consent",
  RETRIEVAL_IN_PROGRESS: "Pulling records",
  COMPLETE: "Connected",
  ERROR: "Error",
  REVOKED: "Revoked",
};

const BADGE_CLASS: Record<HealthExStatus, string> = {
  PENDING_CONSENT: "healthex-badge healthex-badge-pending",
  RETRIEVAL_IN_PROGRESS: "healthex-badge healthex-badge-progress",
  COMPLETE: "healthex-badge healthex-badge-complete",
  ERROR: "healthex-badge healthex-badge-error",
  REVOKED: "healthex-badge healthex-badge-revoked",
};

function HealthExConnectionsInner({
  onError,
}: Pick<HealthExConnectionsProps, "onError">) {
  const client = useHealthExClient();
  const [connections, setConnections] = useState<HealthExLink[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setConnections(await client.listConnections());
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

  const disconnect = async (projectId: string) => {
    setDeleting(projectId);
    setError(null);
    try {
      await client.deleteConnection(projectId);
      setConnections((prev) => prev.filter((c) => c.project_id !== projectId));
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
      <h2>HealthEx connections</h2>

      {loading && <p>Loading connections…</p>}
      {error && <div className="healthex-error">{error}</div>}

      {!loading && !error && connections.length === 0 && (
        <p className="healthex-muted">No HealthEx connections yet.</p>
      )}

      {connections.length > 0 && (
        <ul className="healthex-connection-list">
          {connections.map((c) => (
            <li key={c.project_id} className="healthex-connection">
              <div>
                <div className="healthex-connection-title">
                  <span className={BADGE_CLASS[c.status]}>{BADGE_LABEL[c.status]}</span>
                  HealthEx
                </div>
                <div className="healthex-connection-meta">
                  {c.healthex_patient_id
                    ? `Patient ${c.healthex_patient_id} · `
                    : ""}
                  connected {new Date(c.connected_at).toLocaleDateString()}
                </div>
              </div>
              <button
                type="button"
                className="healthex-disconnect"
                onClick={() => disconnect(c.project_id)}
                disabled={deleting === c.project_id}
              >
                {deleting === c.project_id ? "Removing…" : "Disconnect"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function HealthExConnections({
  apiClient, apiBasePath, className, onError,
}: HealthExConnectionsProps) {
  return (
    <HealthExProvider apiClient={apiClient} apiBasePath={apiBasePath} className={className}>
      <HealthExConnectionsInner onError={onError} />
    </HealthExProvider>
  );
}

export default HealthExConnections;
