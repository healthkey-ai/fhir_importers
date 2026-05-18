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

# TODO: confirm this matches the Airflow connection that points at the Django app's DB.
_POSTGRES_CONN_ID = "postgres-healthkey-etl"


@task(pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=250, weight_rule="upstream")
def validate_params(**kwargs) -> dict[str, Any]:
    """Validate `dag_run.conf` and return a normalized dict for downstream tasks.

    The caller supplies exactly one of `bundle` (inline JSON) or `artifact_key`
    (S3 path). Django's `upload_fhir` endpoint passes the bundle inline; future
    bulk-upload flows would stage to S3 first.
    """
    params = kwargs["params"]
    _logger.info("Params: %s", {k: ("<bundle>" if k == "bundle" else v) for k, v in params.items()})

    artifact_key = params.get("artifact_key")
    bundle = params.get("bundle")
    if artifact_key and bundle:
        raise ValueError("Provide either `artifact_key` or `bundle`, not both")
    if not artifact_key and not bundle:
        raise ValueError("One of `artifact_key` or `bundle` is required")
    if bundle is not None and not isinstance(bundle, dict):
        raise ValueError("`bundle` must be a JSON object (FHIR Bundle resource)")

    fhir_version_value = params.get("fhir_version") or "r4"
    fhir_version = FhirVersion(fhir_version_value)  # raises on unknown version

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
def ingest_bundle(validated_params: dict[str, Any], **kwargs) -> ArtifactKey:
    """Run the FHIR ingestion pipeline against the bundle in `validated_params`.

    Sources the bundle inline (`bundle` key) or from S3 (`artifact_key`),
    runs it through `FhirParsingService`, and uploads the
    `FhirIngestionResult` as a follow-up artifact. Returns that artifact's
    S3 key; pollers can fetch it to surface ingestion status to callers.
    """
    pg_hook = PostgresHook(postgres_conn_id=_POSTGRES_CONN_ID)
    engine = pg_hook.get_sqlalchemy_engine()
    locator = ServiceLocator(engine)

    service = locator.get_fhir_parsing_service()
    artifacts = locator.get_artifact_service()

    provenance_dict = validated_params["provenance"]
    provenance = ProvenanceContext(
        source=ProvenanceSource(provenance_dict["source"]) if provenance_dict["source"] else None,
        source_user_id=provenance_dict.get("source_user_id") or "",
        target_patient_id=provenance_dict.get("target_patient_id"),
        organization_id=provenance_dict["organization_id"],
        modification_reason=provenance_dict["modification_reason"],
    )
    fhir_version = FhirVersion(validated_params["fhir_version"])

    bundle = validated_params.get("bundle")
    if bundle is not None:
        result = service.ingest_from_bundle(
            bundle=bundle,
            fhir_version=fhir_version,
            provenance=provenance,
        )
    else:
        result = service.ingest_from_artifact(
            artifact_key=validated_params["artifact_key"],
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
