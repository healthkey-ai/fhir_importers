"""Tasks shared across every FHIR DAG (fhir_ingest, fhir_extract, fhir_bulk_extract).

The terminal "parse the bundle and write OMOP rows" step is identical in all
three DAGs, so it lives here. Each DAG imports `ingest_artifact` and uses it
as its final task; the per-DAG `validate_params` produces the
`validated_params` dict whose `provenance` key drives the write.
"""
from __future__ import annotations

import logging
from typing import Any

from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook

from entities.omop.provenance_record import ProvenanceSource
from infrastructure.airflow_db.consts import AIRFLOW_POOL_GREAT_BACKGROUND
from services.artifact import ArtifactKey
from services.fhir_parsing import FhirVersion, ProvenanceContext
from services.service_locator import ServiceLocator

_logger = logging.getLogger(__name__)

# Per-deployment override. Same value used by every FHIR task that needs
# a SQLAlchemy engine from Airflow's connection store.
_POSTGRES_CONN_ID = "postgres-healthkey-etl"


def _build_provenance(provenance_dict: dict[str, Any]) -> ProvenanceContext:
    source = provenance_dict.get("source")
    return ProvenanceContext(
        source=ProvenanceSource(source) if source else None,
        source_user_id=provenance_dict.get("source_user_id") or "",
        target_patient_id=provenance_dict.get("target_patient_id"),
        organization_id=provenance_dict.get("organization_id"),
        modification_reason=provenance_dict.get("modification_reason"),
    )


@task(pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=250, weight_rule="upstream")
def ingest_artifact(
    artifact_key: ArtifactKey,
    validated_params: dict[str, Any],
    **kwargs,
) -> ArtifactKey:
    """Parse a staged FHIR Bundle artifact and write OMOP rows.

    Used as the terminal task of all three FHIR DAGs. Returns the S3 key
    of a result-summary artifact (`FhirIngestionResult` JSON).
    """
    pg_hook = PostgresHook(postgres_conn_id=_POSTGRES_CONN_ID)
    engine = pg_hook.get_sqlalchemy_engine()
    locator = ServiceLocator(engine)

    service = locator.get_fhir_parsing_service()
    artifacts = locator.get_artifact_service()

    provenance = _build_provenance(validated_params["provenance"])
    fhir_version = FhirVersion(validated_params["fhir_version"])

    result = service.ingest_from_artifact(
        artifact_key=artifact_key,
        fhir_version=fhir_version,
        provenance=provenance,
    )
    _logger.info(
        "FHIR ingestion finished: created=%d updated=%d errors=%d patients=%d",
        result.created_count,
        result.updated_count,
        len(result.errors),
        len(result.patients),
    )

    result_artifact_key = artifacts.build_artifact_key(
        dag_id=kwargs["dag"].dag_id,
        run_id=kwargs["run_id"],
        task_id=kwargs["task"].task_id,
        key="fhir_ingestion_result.json",
    )
    artifacts.upload_json(result_artifact_key, result.model_dump(mode="json"))
    return result_artifact_key
