"""Scheduled DAG: flag FHIR connections with soon-expiring access tokens.

Per HealthTree Architecture Recommendations v1.1 § 2.1.2:
    "Airflow DAG runs daily: flag connections expiring within 14 days
     → push notification to patient → track re-auth completion."

This DAG handles the SQL flip; the notification is Django's responsibility
— it watches `fhir_connection.status = 'expiring_soon'` and surfaces the
"Reconnect Epic" prompt in the patient settings UI.
"""
import logging

from airflow.decorators import dag
from airflow.models.param import Param

from infrastructure.airflow_db.consts import AIRFLOW_POOL_GREAT_BACKGROUND
from tasks.fhir_token_monitor_tasks import flag_expiring

_logger = logging.getLogger(__name__)


_PARAMS = {
    "expiry_threshold_days": Param(
        type="integer", default=14, minimum=1, maximum=365,
        description=(
            "Flag any `connected` connection whose access_token expires "
            "within this many days. Default 14 matches the v1.1 doc."
        ),
    ),
}


@dag(
    dag_id="fhir_token_monitor",
    schedule_interval="@daily",
    start_date=None,
    catchup=False,
    max_active_runs=1,
    params=_PARAMS,
    tags=["fhir", "scheduled"],
)
def _fhir_token_monitor_dag():
    flag_expiring.override(
        pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=100,
    )()


fhir_token_monitor = _fhir_token_monitor_dag()
