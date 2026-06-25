import httpx


class HealthExSession:
    """Sync httpx wrapper that lazy-mints + caches one org JWT per process.

    Used by CLI / one-shot scripts. Async callers use HealthExClient instead;
    same env vars, different concurrency model.

    Constructor is pure — config arrives via args, never via os.environ.
    `ServiceLocator.get_healthex_session()` is the supported way to build one.
    """

    def __init__(
        self, *, base_url: str, project_id: str, api_key: str, api_secret: str,
    ) -> None:
        self.base = base_url.rstrip("/")
        self.project_id = project_id
        self._api_key = api_key
        self._api_secret = api_secret
        self._http = httpx.Client(timeout=60.0)
        self._org_token: str | None = None

    def org_token(self) -> str:
        if self._org_token is None:
            r = self._http.post(
                f"{self.base}/v1/auth/token",
                json={"apiKey": self._api_key, "apiSecret": self._api_secret},
            )
            if r.status_code not in (200, 201):
                raise RuntimeError(
                    f"auth/token returned {r.status_code}: {r.text[:200]}"
                )
            self._org_token = r.json()["token"]
        return self._org_token

    def org_id(self) -> str:
        import base64
        import json
        _, payload_b64, _ = self.org_token().split(".")
        payload_b64 += "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))["organizationId"]

    def _headers(self, accept: str = "application/json") -> dict[str, str]:
        return {"Authorization": f"Bearer {self.org_token()}", "Accept": accept}

    def get(self, path: str, *, params=None, accept="application/json") -> httpx.Response:
        return self._http.get(self.base + path, params=params, headers=self._headers(accept))

    def post(self, path: str, *, json=None, accept="application/json") -> httpx.Response:
        h = self._headers(accept) | {"Content-Type": "application/json"}
        return self._http.post(self.base + path, json=json, headers=h)

    def delete(self, path: str) -> httpx.Response:
        return self._http.delete(self.base + path, headers=self._headers())
