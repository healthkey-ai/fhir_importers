import { useEffect, useRef, useState } from "react";
import { HealthExProvider } from "./HealthExProvider";
import { useHealthExClient } from "./HealthExContext";
import type { ConnectHealthExProps, HealthExLink } from "./types";

const POLL_INTERVAL_MS = 4000;
const POLL_TIMEOUT_MS = 10 * 60 * 1000;

function ConnectHealthExInner({
  email, firstName, lastName, redirectUri, onConnected, onError,
}: Omit<ConnectHealthExProps, "apiClient" | "apiBasePath" | "className">) {
  const client = useHealthExClient();
  const [link, setLink] = useState<HealthExLink | null>(null);
  const [connecting, setConnecting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const startedAtRef = useRef<number | null>(null);

  // Hydrate existing link on mount so a returning user doesn't get a fresh
  // onboarding URL; /connect is idempotent server-side but checking listings
  // first avoids a roundtrip mint. Pick deterministically: HealthEx supports
  // multiple projects per user (keyed on (user_uid, project_id)), so the
  // server response order is not load-bearing. Until this component takes a
  // projectId prop, prefer the oldest connection (lowest connected_at), which
  // matches "the link the user has been working with".
  useEffect(() => {
    client
      .listConnections()
      .then((conns) => {
        if (conns.length === 0) return;
        const oldest = [...conns].sort((a, b) =>
          a.connected_at.localeCompare(b.connected_at),
        )[0];
        setLink(oldest);
      })
      .catch(() => {
        // Silent — the Connect button works regardless; first interaction
        // will surface any real error.
      });
  }, [client]);

  // Poll for consent + retrieval status whenever we have a link that hasn't
  // resolved a patient_id yet. Fires a reconcile at start to kick the
  // healthex_reconcile DAG; without that kick, /status just returns cached
  // DB state and we'd wait for the periodic tick before seeing patient_id
  // resolve.
  useEffect(() => {
    if (!link || link.healthex_patient_id) return;
    if (startedAtRef.current === null) startedAtRef.current = Date.now();

    // Fire the DAG once at start; subsequent /status polls read the DB
    // row the DAG updates. Rate-limit lives in the backend (/reconcile
    // debounces via last_status_polled_at), so rapid remounts don't need
    // client-side guards. Failure is swallowed — the periodic 30-min DAG
    // is our safety net.
    client.reconcile(link.project_id).catch(() => null);

    let cancelled = false;
    const id = window.setInterval(async () => {
      if (cancelled) return;
      if (Date.now() - (startedAtRef.current ?? 0) > POLL_TIMEOUT_MS) {
        cancelled = true;
        window.clearInterval(id);
        return;
      }
      try {
        const status = await client.getStatus(link.project_id);
        if (cancelled) return;
        if (status.healthex_patient_id) {
          const next: HealthExLink = {
            ...link,
            healthex_patient_id: status.healthex_patient_id,
            status: status.status,
          };
          setLink(next);
          onConnected?.(next);
          window.clearInterval(id);
        }
      } catch (e: unknown) {
        const err = e instanceof Error ? e : new Error(String(e));
        setError(err.message);
        onError?.(err);
      }
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [client, link, onConnected, onError]);

  const connect = async () => {
    setConnecting(true);
    setError(null);
    try {
      const result = await client.connect(email, firstName, lastName);
      setLink(result);
      startedAtRef.current = null;
      if (result.onboarding_url) {
        // HealthEx's SPA reads `redirectUri` from the URL's query params.
        // Use URL.searchParams.set so we don't have to assume whether the
        // onboarding URL already carries a `?xid=...` — matches the
        // pattern healthtree-platform uses on the SvelteKit side.
        const url = new URL(result.onboarding_url);
        if (redirectUri) url.searchParams.set("redirectUri", redirectUri);
        window.open(url.toString(), "_blank", "noopener");
      }
    } catch (e: unknown) {
      const err = e instanceof Error ? e : new Error(String(e));
      setError(err.message);
      onError?.(err);
    } finally {
      setConnecting(false);
    }
  };

  const consented = !!link?.healthex_patient_id;
  const pendingMessage =
    link?.status === "PENDING_CONSENT"
      ? "Waiting for you to finish the HealthEx consent in the other tab…"
      : null;

  return (
    <>
      <h2>Connect HealthEx</h2>
      <p className="healthex-muted">
        Share your medical records via HealthEx (TEFCA / MedAllies / CommonWell).
      </p>

      {error && <div className="healthex-error">{error}</div>}

      {consented && (
        <div className="healthex-success">
          Connected. Patient {link!.healthex_patient_id} · status {link!.status}.
        </div>
      )}

      {!consented && pendingMessage && (
        <div className="healthex-pending">{pendingMessage}</div>
      )}

      {!consented && (
        <button
          type="button"
          onClick={connect}
          disabled={connecting || !email}
        >
          {connecting ? "Opening…" : link ? "Reopen HealthEx" : "Connect HealthEx"}
        </button>
      )}
    </>
  );
}

export function ConnectHealthEx({
  apiClient, apiBasePath, className,
  email, firstName, lastName, redirectUri, onConnected, onError,
}: ConnectHealthExProps) {
  return (
    <HealthExProvider apiClient={apiClient} apiBasePath={apiBasePath} className={className}>
      <ConnectHealthExInner
        email={email}
        firstName={firstName}
        lastName={lastName}
        redirectUri={redirectUri}
        onConnected={onConnected}
        onError={onError}
      />
    </HealthExProvider>
  );
}

export default ConnectHealthEx;
