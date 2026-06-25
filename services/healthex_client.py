import abc
import asyncio
import logging
import time
from dataclasses import dataclass

import httpx


_logger = logging.getLogger(__name__)

# Refresh this many seconds before server-reported expiry so a handed-out token
# has useful in-flight lifetime.
_TOKEN_EXPIRY_SKEW_SECONDS = 60


@dataclass(frozen=True)
class HealthExDataStatus:
    overall_status: str
    vectorization_status: str | None
    updated_at: str | None


class HealthExError(Exception):
    """Outbound call to HealthEx failed (network, non-2xx, malformed body)."""


class BaseHealthExClient(abc.ABC):
    """Outbound HTTP to HealthEx: org-JWT mint + Project-level patient ops."""

    @abc.abstractmethod
    async def get_unique_link(
        self, *, project_id: str, external_id: str,
    ) -> str: ...

    @abc.abstractmethod
    async def find_patient_id_by_external_id(
        self, *, project_id: str, external_id: str,
    ) -> str | None: ...

    @abc.abstractmethod
    async def get_data_retrieval_status(
        self, *, project_id: str, patient_id: str,
    ) -> HealthExDataStatus: ...


class HealthExClient(BaseHealthExClient):
    """httpx-backed adapter. Token is process-cached and refreshed on demand.

    Concurrency: a single in-flight refresh is gated by an asyncio.Lock so
    parallel callers don't burst the auth endpoint after expiry.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        api_secret: str,
    ):
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._api_secret = api_secret
        self._cached_token: str | None = None
        self._cached_until: float = 0.0
        self._refresh_lock = asyncio.Lock()

    async def get_unique_link(
        self, *, project_id: str, external_id: str,
    ) -> str:
        # Response is `text/html` with the URL as the raw body (not JSON);
        # signature on `xid` is server-generated and must not be forged.
        url = f"{self._base_url}/v1/projects/{project_id}/link"
        headers = {
            "Authorization": f"Bearer {await self._access_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            response = await self._http.post(
                url, json={"externalId": external_id}, headers=headers,
            )
        except httpx.HTTPError as exc:
            raise HealthExError(f"POST {url}: {exc}") from exc
        _logger.info("HealthEx POST %s → %s", url, response.status_code)
        if response.status_code not in (200, 201):
            raise HealthExError(
                f"POST {url} returned {response.status_code}: {response.text[:200]}"
            )
        link = response.text.strip()
        if not link.startswith("http"):
            raise HealthExError(
                f"POST {url} returned unexpected body: {response.text[:200]!r}"
            )
        return link

    async def find_patient_id_by_external_id(
        self, *, project_id: str, external_id: str,
    ) -> str | None:
        """Returns patientId once the patient has an OPTED_IN
        PATIENT_DIRECTED_DATA_EXCHANGE consent for this project; None otherwise.

        Hits getPatientConsents which lists every consent record for an
        externalId in a project, in contrast to has-patient-consented-to-study
        which only confirms whether consent exists without exposing patientId.
        """
        url = f"{self._base_url}/v1/patients/consents"
        headers = {
            "Authorization": f"Bearer {await self._access_token()}",
            "Accept": "application/json",
        }
        try:
            response = await self._http.get(
                url,
                params={"externalId": external_id, "projectId": project_id},
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise HealthExError(f"GET {url}: {exc}") from exc
        _logger.info("HealthEx GET %s → %s", url, response.status_code)
        if response.status_code >= 400:
            raise HealthExError(
                f"GET {url} returned {response.status_code}: {response.text[:200]}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise HealthExError(f"GET {url} returned non-JSON body") from exc
        for entry in data.get("results", []) or []:
            cr = (entry or {}).get("consentRecord") or {}
            if (cr.get("consentType") == "PATIENT_DIRECTED_DATA_EXCHANGE"
                    and cr.get("consentStatus") == "OPTED_IN"
                    and cr.get("patientId")):
                return cr["patientId"]
        return None

    async def get_data_retrieval_status(
        self, *, project_id: str, patient_id: str,
    ) -> HealthExDataStatus:
        url = (
            f"{self._base_url}/v1/projects/{project_id}"
            f"/patients/{patient_id}/data-retrieval-status"
        )
        data = await self._get(url)
        return HealthExDataStatus(
            overall_status=data.get("dataRetrievalStatus", "UNKNOWN"),
            vectorization_status=data.get("vectorizationStatus"),
            updated_at=data.get("updatedAt"),
        )

    async def _access_token(self) -> str:
        if self._cached_token and time.time() < self._cached_until:
            return self._cached_token
        async with self._refresh_lock:
            if self._cached_token and time.time() < self._cached_until:
                return self._cached_token
            return await self._fetch_token()

    async def _fetch_token(self) -> str:
        url = f"{self._base_url}/v1/auth/token"
        body = {"apiKey": self._api_key, "apiSecret": self._api_secret}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            response = await self._http.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise HealthExError(f"POST {url}: {exc}") from exc
        # HealthEx returns 201 on token mint (verified on live API).
        if response.status_code not in (200, 201):
            raise HealthExError(
                f"POST {url} returned {response.status_code}: {response.text[:200]}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise HealthExError(f"POST {url} returned non-JSON body") from exc
        token = data.get("token")
        if not token:
            raise HealthExError(f"POST {url} response missing token: {data!r}")
        # `expiration` is an absolute Unix epoch (seconds), not a relative TTL.
        # Skew is applied to the absolute deadline, not converted to a TTL.
        expiration = data.get("expiration")
        if expiration is None:
            self._cached_until = time.time() + (23 * 3600) - _TOKEN_EXPIRY_SKEW_SECONDS
        else:
            self._cached_until = float(expiration) - _TOKEN_EXPIRY_SKEW_SECONDS
        self._cached_token = token
        _logger.info(
            "HealthEx token refreshed (valid for %ds)",
            int(self._cached_until - time.time()),
        )
        return token

    async def _get(self, url: str) -> dict:
        headers = {"Authorization": f"Bearer {await self._access_token()}"}
        try:
            response = await self._http.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise HealthExError(f"GET {url}: {exc}") from exc
        return self._check(response, url, "GET")

    @staticmethod
    def _check(response: httpx.Response, url: str, method: str) -> dict:
        _logger.info("HealthEx %s %s → %s", method, url, response.status_code)
        if response.status_code >= 400:
            raise HealthExError(
                f"{method} {url} returned {response.status_code}: {response.text[:200]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise HealthExError(f"{method} {url} returned non-JSON body") from exc


