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
  // first avoids a roundtrip mint.
  useEffect(() => {
    client
      .listConnections()
      .then((conns) => {
        if (conns.length > 0) setLink(conns[0]);
      })
      .catch(() => {
        // Silent — the Connect button works regardless; first interaction
        // will surface any real error.
      });
  }, [client]);

  // Poll for consent + retrieval status whenever we have a link that hasn't
  // resolved a patient_id yet.
  useEffect(() => {
    if (!link || link.healthex_patient_id) return;
    if (startedAtRef.current === null) startedAtRef.current = Date.now();

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
        // HealthEx's SPA reads `redirectUri` from the URL's hash-query. The
        // signed `xid` is already in the link as `?xid=...`; appending with
        // `&` keeps it inside the same query string after the `#/`.
        const url = redirectUri
          ? `${result.onboarding_url}&redirectUri=${encodeURIComponent(redirectUri)}`
          : result.onboarding_url;
        window.open(url, "_blank", "noopener");
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
