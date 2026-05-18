"""SMART on FHIR extract → ingest DAG.

Triggered by the Django side after a successful OAuth callback (or by a
manual re-sync action / a scheduled incremental sync DAG). Operates as
a single DAG run with three tasks: validate_params → extract_bundle →
ingest_bundle.

DAG conf:
    {
      "connection_id": <int>,                                    REQUIRED
      "fhir_version": "r4" | "stu3" | "dstu2",                   default "r4"
      "sync_mode":    "initial" | "incremental",                 default "initial"
      "provenance_source": <ProvenanceSource>,                   default EHR_SYNC
      "provenance_source_user_id": <str>,
      "provenance_target_patient_id": <str|null>,
      "provenance_organization_id": <int|null>,
      "provenance_modification_reason": <str|null>
    }

Result: an artifact key pointing at the FhirIngestionResult JSON.
"""
import logging

from airflow.decorators import dag
from airflow.models.param import Param

from infrastructure.airflow_db.consts import AIRFLOW_POOL_GREAT_BACKGROUND
from tasks.fhir_common_tasks import ingest_artifact
from tasks.fhir_extract_tasks import extract_bundle, validate_params

_logger = logging.getLogger(__name__)


_PARAMS = {
    "connection_id": Param(
        type="integer",
        minimum=1,
        description=(
            "Primary key of the `fhir_connection` row to extract for. "
            "Django provides this on OAuth callback or manual re-sync."
        ),
    ),
    "fhir_version": Param(
        type="string",
        enum=["r4", "stu3", "dstu2"],
        default="r4",
        description="FHIR version of the source EHR.",
    ),
    "sync_mode": Param(
        type="string",
        enum=["initial", "incremental"],
        default="initial",
        description=(
            "`initial` pulls the patient's full history. `incremental` "
            "uses `_lastUpdated` (or $since for bulk) against the "
            "connection's `last_successful_sync` watermark."
        ),
    ),
    "provenance_source": Param(
        type="string",
        enum=["PATIENT_SELF", "ADMIN_CORRECTION", "EHR_SYNC", "DOCUMENT_EXTRACTION"],
        default="EHR_SYNC",
        description="`provenance_record.source` for every OMOP row this run writes.",
    ),
    "provenance_source_user_id": Param(
        type=["string", "null"],
        default=None,
    ),
    "provenance_target_patient_id": Param(
        type=["string", "null"],
        default=None,
    ),
    "provenance_organization_id": Param(
        type=["integer", "null"],
        default=None,
    ),
    "provenance_modification_reason": Param(
        type=["string", "null"],
        default=None,
    ),
}


@dag(
    dag_id="fhir_extract",
    max_active_runs=20,
    max_active_tasks=20,
    concurrency=100,
    params=_PARAMS,
    catchup=False,
    schedule_interval=None,
)
def _fhir_extract_dag():
    validated = validate_params.override(
        pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=300000
    )()
    artifact = extract_bundle.override(
        pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=300000
    )(validated_params=validated)
    ingest_artifact.override(
        pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=300000
    )(artifact_key=artifact, validated_params=validated)


fhir_extract = _fhir_extract_dag()
