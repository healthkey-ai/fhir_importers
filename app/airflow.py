import abc
import datetime
import logging
from enum import StrEnum
from typing import Any

import httpx


_logger = logging.getLogger(__name__)


class AirflowError(Exception):
    def __init__(self, description: str, url: str, method: str, **kwargs):
        values = {"url": url, "method": method, **kwargs}
        super().__init__(description + " " + ", ".join(f"{k}={v}" for k, v in values.items()))
        self.url = url
        self.method = method


class BadCodeAirflowError(AirflowError):
    def __init__(self, url: str, method: str, response_code: int, response: str):
        self.response_code = response_code
        self.response = response
        super().__init__(
            "Bad response code from Airflow",
            url=url, method=method, response_code=response_code, response=response[:200],
        )


class AirflowDagRunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"


class BaseAirflowClient(abc.ABC):
    @abc.abstractmethod
    async def create_dag_run(self, dag: str, dag_run_prefix: str, conf: dict[str, Any] | None) -> str: ...

    @abc.abstractmethod
    async def get_dag_run_state(self, dag: str, dag_run_id: str) -> AirflowDagRunState: ...


class AirflowClient(BaseAirflowClient):
    def __init__(self, http: httpx.AsyncClient, base_url: str, username: str, password: str):
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._auth = (username, password)

    async def create_dag_run(self, dag: str, dag_run_prefix: str, conf: dict[str, Any] | None) -> str:
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds")
        dag_run_id = f"{dag_run_prefix}__{ts}"
        url = f"{self._base_url}/dags/{dag}/dagRuns"
        data = await self._post(url, {"dag_run_id": dag_run_id, "conf": conf or {}})
        return data["dag_run_id"]

    async def get_dag_run_state(self, dag: str, dag_run_id: str) -> AirflowDagRunState:
        url = f"{self._base_url}/dags/{dag}/dagRuns/{dag_run_id}"
        data = await self._get(url)
        try:
            return AirflowDagRunState(data["state"])
        except (KeyError, ValueError):
            raise AirflowError(f"Unexpected state in response: {data!r}", url=url, method="get")

    async def _post(self, url: str, body: dict) -> dict:
        try:
            response = await self._http.post(url, json=body, auth=self._auth)
        except httpx.HTTPError as e:
            raise AirflowError(str(e), url=url, method="post") from e
        return self._check(response, url, "post")

    async def _get(self, url: str) -> dict:
        try:
            response = await self._http.get(url, auth=self._auth)
        except httpx.HTTPError as e:
            raise AirflowError(str(e), url=url, method="get") from e
        return self._check(response, url, "get")

    @staticmethod
    def _check(response: httpx.Response, url: str, method: str) -> dict:
        _logger.info("Airflow %s %s → %s", method.upper(), url, response.status_code)
        if response.status_code >= 400:
            raise BadCodeAirflowError(
                url=url, method=method,
                response_code=response.status_code, response=response.text,
            )
        return response.json()
