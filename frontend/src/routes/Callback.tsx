import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type FinishResponse } from "../api";

type Status = "pending" | "ok" | "error";

export function Callback() {
  const [params] = useSearchParams();
  const code = params.get("code");
  const state = params.get("state");
  const epicError = params.get("error");
  const epicErrorDescription = params.get("error_description");

  const [status, setStatus] = useState<Status>("pending");
  const [result, setResult] = useState<FinishResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Each authorization code is single-use and the backend pops state atomically.
  // Guard against React 18 StrictMode dev double-mount firing /finish twice.
  const startedRef = useRef<boolean>(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    if (epicError) {
      setStatus("error");
      setErrorMsg(`${epicError}: ${epicErrorDescription ?? ""}`.trim());
      return;
    }
    if (!code || !state) {
      setStatus("error");
      setErrorMsg("Missing code or state in callback URL.");
      return;
    }
    api
      .finish(code, state)
      .then((data) => {
        setResult(data);
        setStatus("ok");
      })
      .catch((e: unknown) => {
        setStatus("error");
        setErrorMsg(String(e));
      });
  }, [code, state, epicError, epicErrorDescription]);

  return (
    <main className="container">
      <h1>MyChart Callback</h1>

      {status === "pending" && <p>Exchanging authorization code…</p>}

      {status === "error" && (
        <>
          <div className="error">{errorMsg}</div>
          <p>
            <Link to="/">Try again</Link>
          </p>
        </>
      )}

      {status === "ok" && result && (
        <>
          <div className="success">Authentication successful.</div>
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
              <code>
                {result.refresh_token
                  ? maskToken(result.refresh_token)
                  : "(not issued)"}
              </code>
            </dd>
            <dt>ID token</dt>
            <dd>
              <code>
                {result.id_token ? maskToken(result.id_token) : "(not issued)"}
              </code>
            </dd>
          </dl>
          <p>
            <Link to="/">Back to start</Link>
          </p>
        </>
      )}
    </main>
  );
}

function maskToken(t: string): string {
  if (t.length <= 16) return t;
  return `${t.slice(0, 12)}…(+${t.length - 12})`;
}
