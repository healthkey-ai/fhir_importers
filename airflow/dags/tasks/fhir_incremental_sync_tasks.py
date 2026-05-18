"""Task bodies for the scheduled `fhir_incremental_sync` DAG.

Pattern: one task enumerates due connections (joined with their institution
so we know which extract DAG to call). A second task is dynamic-mapped
over that list and uses `AirflowClient` to trigger a `fhir_extract` or
`fhir_bulk_extract` DAG run per connection.

Fan-out via the Airflow REST API (rather than `TriggerDagRunOperator`)
keeps the per-row target DAG selection clean and matches the existing
cancerbot-etl pattern.
"""
from __future__ import annotations

import logging
from typing import Any

from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook

from infrastructure.airflow_client import AirflowDag
from infrastructure.airflow_db.consts import AIRFLOW_POOL_GREAT_BACKGROUND
from services.service_locator import ServiceLocator

_logger = logging.getLogger(__name__)

_POSTGRES_CONN_ID = "postgres-healthkey-etl"


@task(pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=100, weight_rule="upstream")
def enumerate_due_connections(**kwargs) -> list[dict[str, Any]]:
    """Return rows the scheduler should fire extract runs for.

    Each entry carries enough metadata for the downstream mapped task to
    pick `fhir_extract` vs `fhir_bulk_extract` without another DB read.
    """
    params = kwargs["params"]
    min_age_hours = int(params.get("min_age_hours") or 24)
    limit = int(params.get("limit") or 500)

    pg_hook = PostgresHook(postgres_conn_id=_POSTGRES_CONN_ID)
    engine = pg_hook.get_sqlalchemy_engine()
    locator = ServiceLocator(engine)

    due = locator.get_fhir_connection_repository().list_due_for_sync(
        min_age_hours=min_age_hours, limit=limit,
    )
    _logger.info(
        "fhir_incremental_sync: %d connections due (min_age_hours=%d limit=%d)",
        len(due), min_age_hours, limit,
    )
    return [
        {
            "connection_id": row.connection_id,
            "institution_slug": row.institution_slug,
            "supports_bulk_export": row.supports_bulk_export,
            "last_successful_sync": (
                row.last_successful_sync.isoformat() if row.last_successful_sync else None
            ),
        }
        for row in due
    ]


@task(pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=100, weight_rule="upstream")
def trigger_extract_for_connection(connection_info: dict[str, Any], **kwargs) -> str:
    """Fire a fhir_extract or fhir_bulk_extract DAG run for one connection.

    Returns the assigned dag_run_id (Airflow auto-XComs it, so the
    operator log shows which downstream run came from which mapped task).
    """
    locator = ServiceLocator()
    client = locator.get_airflow_client()

    target_dag = (
        AirflowDag.FHIR_BULK_EXTRACT
        if connection_info.get("supports_bulk_export")
        else AirflowDag.FHIR_EXTRACT
    )

    conf = {
        "connection_id": connection_info["connection_id"],
        "fhir_version": "r4",
        "sync_mode": "incremental",
        "provenance_source": "EHR_SYNC",
    }

    dag_run_id = client.create_dag_run(
        dag=target_dag,
        conf=conf,
        dag_run_prefix=f"scheduled-{connection_info['connection_id']}",
    )
    _logger.info(
        "Triggered %s for connection_id=%s (slug=%s) → dag_run_id=%s",
        target_dag.value,
        connection_info["connection_id"],
        connection_info.get("institution_slug"),
        dag_run_id,
    )
    return dag_run_id
