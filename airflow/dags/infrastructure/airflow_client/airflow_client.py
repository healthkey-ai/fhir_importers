import abc
from typing import Any, Dict

from infrastructure.airflow_client.airflow_types import AirflowDag, DagRunId, TaskId, AirflowDagRunState


class AirflowClient(abc.ABC):
    @abc.abstractmethod
    def get_dag_run_web_url(self, dag_id: str, dag_run_id: str) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def create_dag_run(self, dag: AirflowDag, conf: Dict[str, Any] | None, dag_run_prefix: str | None = None) -> DagRunId:
        """Create a new DAG run."""
        raise NotImplementedError

    @abc.abstractmethod
    def set_dag_run_state(self, dag: AirflowDag, dag_run_id: DagRunId, state: AirflowDagRunState) -> None:
        """Set the state of a DAG run."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_dag_run_state(self, dag: AirflowDag, dag_run_id: DagRunId) -> AirflowDagRunState:
        """Get the state of a DAG run."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_dag_run_task_instances(self, dag: AirflowDag, dag_run_id: DagRunId) -> Dict[str, Any]:
        """Get the task instances of a DAG run."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_xcom_entry(self, dag: AirflowDag, dag_run_id: DagRunId, task_id: TaskId, key: str) -> Any:
        """Get an XCom entry."""
        raise NotImplementedError
