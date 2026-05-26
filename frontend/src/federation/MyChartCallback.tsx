import { useEffect, useRef, useState } from "react";
import { MyChartProvider } from "./MyChartProvider";
import { useMyChartClient } from "./MyChartContext";
import type { FinishResult, MyChartCallbackProps } from "./types";

type Status = "pending" | "ok" | "error";

function maskToken(t: string): string {
  if (t.length <= 16) return t;
  return `${t.slice(0, 12)}…(+${t.length - 12})`;
}

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
  const [result, setResult] = useState<FinishResult | null>(null);
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
          <div className="mychart-success">Authentication successful.</div>
          <dl>
            <dt>Patient</dt>
            <dd>{result.patient ?? <em>not provided</em>}</dd>
            <dt>Scope</dt>
            <dd>
              <code>{result.scope ?? "(none)"}</code>
            </dd>
            <dt>Expires in</dt>
            <dd>{result.expires_in}s</dd>
            <dt>Access token</dt>
            <dd>
              <code>{maskToken(result.access_token)}</code>
            </dd>
            <dt>Refresh token</dt>
            <dd>
              <code>{result.refresh_token ? maskToken(result.refresh_token) : "(not issued)"}</code>
            </dd>
            <dt>ID token</dt>
            <dd>
              <code>{result.id_token ? maskToken(result.id_token) : "(not issued)"}</code>
            </dd>
          </dl>
        </>
      )}
    </>
  );
}

export function MyChartCallback({
  apiBaseUrl,
  className,
  code,
  state,
  onSuccess,
  onError,
}: MyChartCallbackProps) {
  return (
    <MyChartProvider apiBaseUrl={apiBaseUrl} className={className}>
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
