import { useCallback, useEffect, useState } from "react";
import { HealthExProvider } from "./HealthExProvider";
import { useHealthExClient } from "./HealthExContext";
import type {
  HealthExConnectionsProps,
  HealthExIngestResult,
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
  const [ingesting, setIngesting] = useState<string | null>(null);
  // Keyed by project_id so multiple connections show independent results.
  const [ingestResults, setIngestResults] = useState<
    Record<string, HealthExIngestResult>
  >({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await client.listConnections();
      setConnections(rows);
      // Reconcile with HealthEx: `listConnections` returns our DB state,
      // which can lag if the user revoked consent on HealthEx's own UI.
      // Firing `/status` per row on mount forces the backend to re-check
      // getPatientConsents; the response updates our DB and reflects a
      // revocation as status=REVOKED. Fire-and-forget — the second render
      // picks up refreshed rows.
      const refreshed = await Promise.all(
        rows.map((r) =>
          r.healthex_patient_id
            ? client
                .getStatus(r.project_id)
                .then((s) => ({ ...r, status: s.status }))
                .catch(() => r)
            : Promise.resolve(r),
        ),
      );
      setConnections(refreshed);
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

  const ingest = async (projectId: string) => {
    setIngesting(projectId);
    setError(null);
    try {
      const result = await client.ingest(projectId);
      setIngestResults((prev) => ({ ...prev, [projectId]: result }));
    } catch (e: unknown) {
      const err = e instanceof Error ? e : new Error(String(e));
      setError(err.message);
      onError?.(err);
    } finally {
      setIngesting(null);
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
              <div className="healthex-connection-actions">
                {c.healthex_patient_id && (
                  <button
                    type="button"
                    className="healthex-ingest"
                    onClick={() => ingest(c.project_id)}
                    disabled={ingesting === c.project_id}
                    title="Trigger the healthex_extract Airflow DAG — persists to OMOP"
                  >
                    {ingesting === c.project_id
                      ? "Kicking off…"
                      : "Sync to OMOP"}
                  </button>
                )}
                <button
                  type="button"
                  className="healthex-disconnect"
                  onClick={() => disconnect(c.project_id)}
                  disabled={deleting === c.project_id}
                >
                  {deleting === c.project_id ? "Removing…" : "Disconnect"}
                </button>
              </div>
              {ingestResults[c.project_id] && (
                <div className="healthex-ingest-result">
                  Airflow DAG run queued —{" "}
                  <code>{ingestResults[c.project_id].dag_run_id}</code>
                </div>
              )}
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
