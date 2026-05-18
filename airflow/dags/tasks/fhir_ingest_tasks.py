"""Tasks for the `fhir_ingest` DAG (DAG 1 — parse an S3-staged bundle).

This DAG's job is "given a FHIR Bundle, write OMOP rows". The bundle
arrives in one of two shapes (mutually exclusive):

  - `artifact_key`: already staged in S3 (the cancerbot-etl pattern, also
    used by the bulk/extract DAGs when they hand off to this code path).
  - `bundle`: inline JSON object in the DAG conf (the Django
    `upload_fhir` view passes this for direct file uploads — small bundles).

When the bundle is inline, this DAG stages it into S3 as its first task so
the rest of the pipeline operates uniformly on artifact keys. The terminal
ingest task is shared with the other FHIR DAGs (`fhir_common_tasks.ingest_artifact`).
"""
from __future__ import annotations

import logging
from typing import Any

from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook

from entities.omop.provenance_record import ProvenanceSource
from infrastructure.airflow_db.consts import AIRFLOW_POOL_GREAT_BACKGROUND
from services.artifact import ArtifactKey
from services.fhir_parsing import FhirVersion
from services.service_locator import ServiceLocator

_logger = logging.getLogger(__name__)

_POSTGRES_CONN_ID = "postgres-healthkey-etl"


@task(pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=250, weight_rule="upstream")
def validate_params(**kwargs) -> dict[str, Any]:
    """Validate `dag_run.conf`. Caller supplies exactly one of `artifact_key`
    or `bundle` (inline JSON object). Provenance defaults to no source."""
    params = kwargs["params"]
    _logger.info(
        "Params: %s",
        {k: ("<bundle>" if k == "bundle" else v) for k, v in params.items()},
    )

    artifact_key = params.get("artifact_key")
    bundle = params.get("bundle")
    if artifact_key and bundle:
        raise ValueError("Provide either `artifact_key` or `bundle`, not both")
    if not artifact_key and not bundle:
        raise ValueError("One of `artifact_key` or `bundle` is required")
    if bundle is not None and not isinstance(bundle, dict):
        raise ValueError("`bundle` must be a JSON object (FHIR Bundle resource)")

    fhir_version = FhirVersion(params.get("fhir_version") or "r4")

    provenance_source_value = params.get("provenance_source")
    provenance_source: ProvenanceSource | None = (
        ProvenanceSource(provenance_source_value) if provenance_source_value else None
    )
    modification_reason = params.get("provenance_modification_reason")
    if provenance_source == ProvenanceSource.ADMIN_CORRECTION and not modification_reason:
        raise ValueError(
            "`provenance_modification_reason` is required when "
            "`provenance_source` is ADMIN_CORRECTION"
        )

    return {
        "artifact_key": artifact_key,
        "bundle": bundle,
        "fhir_version": fhir_version.value,
        "provenance": {
            "source": provenance_source.value if provenance_source else None,
            "source_user_id": params.get("provenance_source_user_id") or "",
            "target_patient_id": params.get("provenance_target_patient_id"),
            "organization_id": params.get("provenance_organization_id"),
            "modification_reason": modification_reason,
        },
    }


@task(pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=250, weight_rule="upstream")
def stage_inline_bundle(validated_params: dict[str, Any], **kwargs) -> ArtifactKey:
    """Resolve the artifact_key the ingest step will read.

    - If the caller supplied an `artifact_key`, pass it through.
    - If the caller supplied an inline `bundle`, upload it to S3 first so
      the rest of the pipeline operates uniformly on artifact keys.
    """
    artifact_key = validated_params.get("artifact_key")
    if artifact_key:
        return artifact_key

    bundle = validated_params.get("bundle")
    if bundle is None:
        # `validate_params` already enforces this, but defend in depth.
        raise ValueError("Neither artifact_key nor bundle is present in validated_params")

    locator = ServiceLocator(PostgresHook(postgres_conn_id=_POSTGRES_CONN_ID).get_sqlalchemy_engine())
    artifacts = locator.get_artifact_service()
    new_artifact_key = artifacts.build_artifact_key(
        dag_id=kwargs["dag"].dag_id,
        run_id=kwargs["run_id"],
        task_id=kwargs["task"].task_id,
        key="staged_bundle.json",
    )
    artifacts.upload_json(new_artifact_key, bundle)
    return new_artifact_key
