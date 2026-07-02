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

      // On-demand reconcile is only worth firing for rows still waiting on
      // patient_id resolution (PENDING_CONSENT). Rows with healthex_patient_id
      // already resolved get revocation checks from the periodic 30-min DAG
      // tick — that's acceptable freshness and keeps every page refresh from
      // spawning N Airflow tasks.
      const needsReconcile = rows.filter((r) => !r.healthex_patient_id);
      if (needsReconcile.length === 0) return;

      // Per-project sessionStorage debounce guards against rapid refresh
      // (dev, back-forward navigation) piling up redundant DAG runs.
      const DEBOUNCE_MS = 30_000;
      const now = Date.now();
      const shouldReconcile = needsReconcile.filter((r) => {
        const key = `healthex.reconcile.lastFired.${r.project_id}`;
        const last = Number(sessionStorage.getItem(key)) || 0;
        if (now - last < DEBOUNCE_MS) return false;
        sessionStorage.setItem(key, String(now));
        return true;
      });
      if (shouldReconcile.length === 0) return;

      await Promise.all(
        shouldReconcile.map((r) =>
          client.reconcile(r.project_id).catch(() => null),
        ),
      );

      // Bounded polling: refetch listConnections up to N times with a
      // small delay to let the DAG catch up. Stops early once each
      // reconciling row's `last_status_polled_at` has advanced.
      const initialPolled = new Map(
        shouldReconcile.map(
          (r) => [r.project_id, r.last_status_polled_at] as const,
        ),
      );
      const POLL_MS = 3000;
      const POLL_MAX_ATTEMPTS = 5; // ~15s ceiling; DAG typically finishes in <10s
      for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
        const next = await client.listConnections();
        setConnections(next);
        const allAdvanced = shouldReconcile.every((seed) => {
          const current = next.find((n) => n.project_id === seed.project_id);
          return (
            current !== undefined
            && current.last_status_polled_at !== initialPolled.get(seed.project_id)
          );
        });
        if (allAdvanced) break;
      }
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
