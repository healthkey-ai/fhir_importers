import datetime
import logging
from typing import Dict, Any
import urllib.parse

import requests

from infrastructure.airflow_client.airflow_client import AirflowClient
from infrastructure.airflow_client.airflow_errors import AirflowError, BadCodeAirflowError
from infrastructure.airflow_client.airflow_types import AirflowDag, DagRunId, AirflowDagRunState, TaskId

_logger = logging.getLogger(__name__)


class AirflowClientImplementation(AirflowClient):
    def __init__(self, airflow_url: str, airflow_username: str, airflow_password: str):
        self._web_url = "http://airflow.cancerbot.org:8080"
        self._base_url = airflow_url
        self._username = airflow_username
        self._password = airflow_password

    def get_dag_run_web_url(self, dag_id: str, dag_run_id: str) -> str:
        encoded_dag_run_id = urllib.parse.quote(dag_run_id, safe="")
        return self._web_url + f"/dags/{dag_id}/grid?dag_run_id={encoded_dag_run_id}&tab=graph"

    def create_dag_run(self, dag: AirflowDag, conf: Dict[str, Any] | None, dag_run_prefix: str | None = None) -> DagRunId:
        url = self._base_url + "/dags/" + dag.value + "/dagRuns"
        payload = {
            "conf": conf,
        }
        if dag_run_prefix:
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds")
            dag_run_id = dag_run_prefix + "__" + timestamp
            payload["dag_run_id"] = dag_run_id
        return self._request_with_error_handling(url, "post", payload).json()["dag_run_id"]

    def get_dag_run_state(self, dag: AirflowDag, dag_run_id: DagRunId) -> AirflowDagRunState:
        url = self._base_url + f"/dags/{dag.value}/dagRuns/{dag_run_id}"
        state_str = self._request_with_error_handling(url, "get", None).json()["state"]
        try:
            return AirflowDagRunState(state_str)
        except KeyError:
            raise AirflowError(
                description=f"Unexpected state {state_str} (missing enum value?)",
                url=url,
                method="get",
            )

    def set_dag_run_state(self, dag: AirflowDag, dag_run_id: DagRunId, state: AirflowDagRunState) -> None:
        url = self._base_url + f"/dags/{dag.value}/dagRuns/{dag_run_id}"
        payload = {
            "state": state.value,
        }
        self._request_with_error_handling(url, "patch", payload)

    def get_dag_run_task_instances(self, dag: AirflowDag, dag_run_id: DagRunId) -> Dict[str, Any]:
        url = self._base_url + f"/dags/{dag.value}/dagRuns/{dag_run_id}/taskInstances"
        return self._request_with_error_handling(url, "get", None).json()

    def get_xcom_entry(self, dag: AirflowDag, dag_run_id: DagRunId, task_id: TaskId, key: str) -> Any:
        url = self._base_url + f"/dags/{dag.value}/dagRuns/{dag_run_id}/taskInstances/{task_id}/xcomEntries/{key}"
        return self._request_with_error_handling(url, "get", None).json()["value"]

    def _request_with_error_handling(self, url: str, method: str, payload: Dict[str, Any] | None) -> requests.Response:
        try:
            return self._request(url, method, payload)
        except AirflowError as e:
            raise e
        except Exception as e:
            raise AirflowError(
                description=str(e),
                url=url,
                method=method,
            ) from e

    def _request(self, url: str, method: str, payload: Dict[str, Any]) -> requests.Response:
        started_at = datetime.datetime.now()
        response = requests.request(
            method=method,
            url=url,
            auth=(self._username, self._password),
            json=payload
        )
        elapsed = datetime.datetime.now() - started_at
        _logger.info(f"Request url={url} method={method} elapsed={elapsed} "
                     f"response_code={response.status_code} response={response.text}")
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise BadCodeAirflowError(
                url=url,
                method=method,
                elapsed=elapsed,
                response_code=response.status_code,
                response=response.text
            ) from e

        return response
