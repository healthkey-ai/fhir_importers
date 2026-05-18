"""Tasks for the `fhir_extract` DAG.

Sequence (all inside one DAG run):
  validate_params  → normalize + sanity-check the conf
  extract_bundle   → refresh token, pull bundle from EHR, upload to S3
  ingest_bundle    → parse + write OMOP rows via FhirParsingService
"""
from __future__ import annotations

import logging
from typing import Any

from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook

from entities.omop.provenance_record import ProvenanceSource
from infrastructure.airflow_db.consts import AIRFLOW_POOL_GREAT_BACKGROUND
from services.artifact import ArtifactKey
from services.fhir_extract import SyncMode
from services.fhir_parsing import FhirVersion, ProvenanceContext
from services.service_locator import ServiceLocator
from tasks.fhir_common_tasks import log_artifact

_logger = logging.getLogger(__name__)

# TODO: confirm against the actual Airflow connection name in deployment.
_POSTGRES_CONN_ID = "postgres-healthkey-etl"


@task(pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=250, weight_rule="upstream")
def validate_params(**kwargs) -> dict[str, Any]:
    """Validate `dag_run.conf` for a fhir_extract trigger.

    Required: connection_id.
    Optional: fhir_version (default r4), sync_mode (default 'initial'),
              provenance_* (defaults to source=EHR_SYNC).
    """
    params = kwargs["params"]
    _logger.info("Params: %s", params)

    connection_id = params.get("connection_id")
    if not isinstance(connection_id, int) or connection_id <= 0:
        raise ValueError("`connection_id` (positive integer) is required")

    fhir_version = FhirVersion(params.get("fhir_version") or "r4")
    sync_mode = SyncMode(params.get("sync_mode") or "initial")

    # Provenance defaults to EHR_SYNC because this DAG only fires after a
    # successful patient OAuth; that *is* an EHR sync.
    provenance_source = params.get("provenance_source") or ProvenanceSource.EHR_SYNC.value
    ProvenanceSource(provenance_source)  # validates enum

    return {
        "connection_id": connection_id,
        "fhir_version": fhir_version.value,
        "sync_mode": sync_mode.value,
        "provenance": {
            "source": provenance_source,
            "source_user_id": params.get("provenance_source_user_id") or "",
            "target_patient_id": params.get("provenance_target_patient_id"),
            "organization_id": params.get("provenance_organization_id"),
            "modification_reason": params.get("provenance_modification_reason"),
        },
    }


@task(pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=250, weight_rule="upstream")
def extract_bundle(validated_params: dict[str, Any], **kwargs) -> ArtifactKey:
    """Pull the FHIR Bundle from the EHR using the stored connection.

    Returns the S3 artifact key the bundle landed at; ingest_bundle reads it.
    """
    pg_hook = PostgresHook(postgres_conn_id=_POSTGRES_CONN_ID)
    engine = pg_hook.get_sqlalchemy_engine()
    locator = ServiceLocator(engine)

    extract_service = locator.get_fhir_extract_service()
    artifacts = locator.get_artifact_service()

    artifact_key = artifacts.build_artifact_key(
        dag_id=kwargs["dag"].dag_id,
        run_id=kwargs["run_id"],
        task_id=kwargs["task"].task_id,
        key="fhir_bundle.json",
    )

    extract_service.extract(
        connection_id=validated_params["connection_id"],
        mode=SyncMode(validated_params["sync_mode"]),
        artifact_key=artifact_key,
    )
    log_artifact("Extracted bundle (paginated $everything)", artifacts, artifact_key)
    return artifact_key


# NOTE: The terminal "parse bundle → write OMOP" task that previously lived
# here has moved to `tasks/fhir_common_tasks.ingest_artifact` so the
# fhir_ingest, fhir_extract, and fhir_bulk_extract DAGs all share one
# implementation. The DAG below imports it directly.
