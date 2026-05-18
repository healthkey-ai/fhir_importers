"""Scheduled DAG: fan out incremental FHIR syncs for due connections.

Per HealthTree Architecture Recommendations v1.1 § 2.3.2:
    "Airflow DAG triggers sync on a per-patient schedule — patients who
     just connected sync daily, stable long-term patients sync weekly."

For first version we use a single `min_age_hours` threshold; finer cadence
classes (per-status, per-institution) can be added by extending
`FhirConnectionRepository.list_due_for_sync`.

Fan-out: dynamic task mapping (`.expand()`) over the list of due connections
spawns one `trigger_extract_for_connection` task per row. Each mapped task
fires a `fhir_extract` (paginated) or `fhir_bulk_extract` ($export) DAG run
via the Airflow REST API.
"""
import logging

from airflow.decorators import dag
from airflow.models.param import Param

from infrastructure.airflow_db.consts import AIRFLOW_POOL_GREAT_BACKGROUND
from tasks.fhir_incremental_sync_tasks import (
    enumerate_due_connections,
    trigger_extract_for_connection,
)

_logger = logging.getLogger(__name__)


_PARAMS = {
    "min_age_hours": Param(
        type="integer", default=24, minimum=1,
        description=(
            "Sync any connection whose last_successful_sync is older than "
            "this many hours (or NULL). Default 24h."
        ),
    ),
    "limit": Param(
        type="integer", default=500, minimum=1,
        description=(
            "Cap the number of connections processed per scheduler run, "
            "to avoid runaway fan-out if the DB has thousands of stale "
            "connections from a multi-day outage."
        ),
    ),
}


@dag(
    dag_id="fhir_incremental_sync",
    schedule_interval="@daily",
    start_date=None,
    catchup=False,
    max_active_runs=1,
    max_active_tasks=50,        # cap concurrent fan-out
    params=_PARAMS,
    tags=["fhir", "scheduled"],
)
def _fhir_incremental_sync_dag():
    due = enumerate_due_connections.override(
        pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=100,
    )()
    trigger_extract_for_connection.override(
        pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=100,
    ).expand(connection_info=due)


fhir_incremental_sync = _fhir_incremental_sync_dag()
