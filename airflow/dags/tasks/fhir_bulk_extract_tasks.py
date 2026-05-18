"""Tasks for the `fhir_bulk_extract` DAG.

Sequence:
  validate_params       → normalize conf
  bulk_extract_bundle   → initiate $export, poll until done, download all
                          NDJSON, stitch into a Bundle, upload to S3
  ingest_artifact       → shared with fhir_ingest / fhir_extract

This DAG is for institutions whose `supports_bulk_export = True`. For
others, use `fhir_extract` (paginated `$everything`).
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
from services.fhir_parsing import FhirVersion
from services.service_locator import ServiceLocator

_logger = logging.getLogger(__name__)

_POSTGRES_CONN_ID = "postgres-healthkey-etl"


@task(pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=250, weight_rule="upstream")
def validate_params(**kwargs) -> dict[str, Any]:
    """Validate `dag_run.conf` for fhir_bulk_extract."""
    params = kwargs["params"]
    _logger.info("Params: %s", params)

    connection_id = params.get("connection_id")
    if not isinstance(connection_id, int) or connection_id <= 0:
        raise ValueError("`connection_id` (positive integer) is required")

    fhir_version = FhirVersion(params.get("fhir_version") or "r4")
    sync_mode = SyncMode(params.get("sync_mode") or "initial")

    resource_types = params.get("resource_types") or []
    if not isinstance(resource_types, list):
        raise ValueError("`resource_types` must be a list of FHIR resource type names")

    poll_timeout_seconds = int(params.get("poll_timeout_seconds") or 3600)

    provenance_source = params.get("provenance_source") or ProvenanceSource.EHR_SYNC.value
    ProvenanceSource(provenance_source)  # raises on bad enum

    return {
        "connection_id": connection_id,
        "fhir_version": fhir_version.value,
        "sync_mode": sync_mode.value,
        "resource_types": resource_types,
        "poll_timeout_seconds": poll_timeout_seconds,
        "provenance": {
            "source": provenance_source,
            "source_user_id": params.get("provenance_source_user_id") or "",
            "target_patient_id": params.get("provenance_target_patient_id"),
            "organization_id": params.get("provenance_organization_id"),
            "modification_reason": params.get("provenance_modification_reason"),
        },
    }


@task(pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=250, weight_rule="upstream")
def bulk_extract_bundle(validated_params: dict[str, Any], **kwargs) -> ArtifactKey:
    """Initiate $export, poll, download manifest, stitch into a Bundle artifact.

    TODO(performance): replace the in-task polling loop with an Airflow
    deferrable operator so workers aren't held across long EHR exports.
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

    extract_service.bulk_extract(
        connection_id=validated_params["connection_id"],
        mode=SyncMode(validated_params["sync_mode"]),
        artifact_key=artifact_key,
        resource_types=validated_params.get("resource_types") or None,
        poll_timeout_seconds=validated_params.get("poll_timeout_seconds", 3600),
    )
    return artifact_key
