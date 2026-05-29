import { useEffect, useRef, useState } from "react";
import { MyChartProvider } from "./MyChartProvider";
import { useMyChartClient } from "./MyChartContext";
import type { ConnectionResult, MyChartCallbackProps } from "./types";

type Status = "pending" | "ok" | "error";

function MyChartCallbackInner({
  code: codeProp,
  state: stateProp,
  onSuccess,
  onError,
}: Pick<MyChartCallbackProps, "code" | "state" | "onSuccess" | "onError">) {
  const client = useMyChartClient();

  // Props win; otherwise read from the current URL (the host route Epic redirects to).
  const params = new URLSearchParams(window.location.search);
  const code = codeProp ?? params.get("code");
  const state = stateProp ?? params.get("state");
  const epicError = params.get("error");
  const epicErrorDescription = params.get("error_description");

  const [status, setStatus] = useState<Status>("pending");
  const [result, setResult] = useState<ConnectionResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // The authorization code is single-use and the backend pops state atomically.
  // Guard against React 18 StrictMode dev double-mount firing /finish twice.
  const startedRef = useRef<boolean>(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    if (epicError) {
      const msg = `${epicError}: ${epicErrorDescription ?? ""}`.trim();
      setStatus("error");
      setErrorMsg(msg);
      onError?.(new Error(msg));
      return;
    }
    if (!code || !state) {
      const msg = "Missing code or state in callback URL.";
      setStatus("error");
      setErrorMsg(msg);
      onError?.(new Error(msg));
      return;
    }
    client
      .finish(code, state)
      .then((data) => {
        setResult(data);
        setStatus("ok");
        onSuccess?.(data);
      })
      .catch((e: unknown) => {
        const err = e instanceof Error ? e : new Error(String(e));
        setStatus("error");
        setErrorMsg(err.message);
        onError?.(err);
      });
  }, [client, code, state, epicError, epicErrorDescription, onSuccess, onError]);

  return (
    <>
      <h2>MyChart Callback</h2>

      {status === "pending" && <p>Exchanging authorization code…</p>}

      {status === "error" && <div className="mychart-error">{errorMsg}</div>}

      {status === "ok" && result && (
        <>
          <div className="mychart-success">MyChart connected successfully.</div>
          {/* Tokens are persisted server-side; this is non-sensitive metadata. */}
          <dl>
            <dt>Organization</dt>
            <dd>{result.organization_alias}</dd>
            <dt>Patient</dt>
            <dd>{result.patient ?? <em>not provided</em>}</dd>
            <dt>Scope</dt>
            <dd>
              <code>{result.scope ?? "(none)"}</code>
            </dd>
            <dt>Connected</dt>
            <dd>{new Date(result.connected_at).toLocaleString()}</dd>
          </dl>
        </>
      )}
    </>
  );
}

export function MyChartCallback({
  apiClient,
  apiBasePath,
  className,
  code,
  state,
  onSuccess,
  onError,
}: MyChartCallbackProps) {
  return (
    <MyChartProvider apiClient={apiClient} apiBasePath={apiBasePath} className={className}>
      <MyChartCallbackInner
        code={code}
        state={state}
        onSuccess={onSuccess}
        onError={onError}
      />
    </MyChartProvider>
  );
}

export default MyChartCallback;
