import { useEffect, useState } from "react";
import { api, type Organization } from "../api";
import { OrganizationCombobox } from "../components/OrganizationCombobox";

export function Landing() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selected, setSelected] = useState<Organization | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<boolean>(false);

  useEffect(() => {
    api
      .listOrganizations()
      .then((data) => setOrgs(data))
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const connect = async () => {
    if (!selected) return;
    setConnecting(true);
    setError(null);
    try {
      const { authorization_url } = await api.start(selected.alias);
      window.location.href = authorization_url;
    } catch (e: unknown) {
      setError(String(e));
      setConnecting(false);
    }
  };

  return (
    <main className="container">
      <h1>MyChart Integration</h1>
      <p className="muted">
        Connect your MyChart account to share clinical data with this app.
      </p>

      {loading && <p>Loading organizations…</p>}
      {error && <div className="error">{error}</div>}

      {!loading && (
        <>
          <label htmlFor="org">Hospital / organization</label>
          <OrganizationCombobox
            organizations={orgs}
            value={selected}
            onChange={setSelected}
            disabled={connecting || orgs.length === 0}
            placeholder="Start typing a hospital name…"
          />

          <button
            type="button"
            onClick={connect}
            disabled={!selected || connecting}
          >
            {connecting ? "Redirecting…" : "Connect MyChart"}
          </button>
        </>
      )}
    </main>
  );
}
