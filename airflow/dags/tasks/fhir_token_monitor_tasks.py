"""Task body for the scheduled `fhir_token_monitor` DAG.

Single responsibility: flip `fhir_connection.status` from `connected` to
`expiring_soon` for rows whose `expires_at` falls inside the configured
window. Doesn't notify users directly — that's Django's job (the column
flip is the signal Django watches).
"""
from __future__ import annotations

import logging
from typing import Any

from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook

from infrastructure.airflow_db.consts import AIRFLOW_POOL_GREAT_BACKGROUND
from services.service_locator import ServiceLocator

_logger = logging.getLogger(__name__)

_POSTGRES_CONN_ID = "postgres-healthkey-etl"


@task(pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=100, weight_rule="upstream")
def flag_expiring(**kwargs) -> dict[str, Any]:
    """Bump `connected` connections expiring soon → `expiring_soon`.

    Returns a small summary the Airflow UI surfaces via XCom for ops visibility.
    """
    params = kwargs["params"]
    days = int(params.get("expiry_threshold_days") or 14)

    pg_hook = PostgresHook(postgres_conn_id=_POSTGRES_CONN_ID)
    engine = pg_hook.get_sqlalchemy_engine()
    locator = ServiceLocator(engine)

    flagged = locator.get_fhir_connection_repository().flag_expiring_tokens(
        days_until_expiry=days,
    )
    _logger.info(
        "fhir_token_monitor: flagged %d connections as expiring_soon "
        "(threshold %d days)",
        flagged, days,
    )
    return {"flagged_count": flagged, "expiry_threshold_days": days}
