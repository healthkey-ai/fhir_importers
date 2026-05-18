"""SMART on FHIR bulk extract → ingest DAG (DAG 3).

Uses FHIR `$export` (Bulk Data API). The patient's records are produced
asynchronously by the EHR and downloaded as NDJSON files, then stitched
into a Bundle and parsed.

For institutions without `supports_bulk_export = True`, use the
`fhir_extract` DAG (paginated `$everything`) instead.

DAG conf:
    {
      "connection_id": <int>,                                    REQUIRED
      "fhir_version": "r4" | "stu3" | "dstu2",                   default "r4"
      "sync_mode":    "initial" | "incremental",                 default "initial"
      "resource_types": ["Patient","Condition","Observation",...],
                      # optional; defaults to whole-record export
      "poll_timeout_seconds": <int>,                             default 3600 (1h)
      "provenance_source": ...,                                  default EHR_SYNC
      ...same provenance fields as the other FHIR DAGs
    }
"""
import logging

from airflow.decorators import dag
from airflow.models.param import Param

from infrastructure.airflow_db.consts import AIRFLOW_POOL_GREAT_BACKGROUND
from tasks.fhir_bulk_extract_tasks import bulk_extract_bundle, validate_params
from tasks.fhir_common_tasks import ingest_artifact

_logger = logging.getLogger(__name__)


_PARAMS = {
    "connection_id": Param(
        type="integer",
        minimum=1,
        description="Primary key of the `fhir_connection` row to export for.",
    ),
    "fhir_version": Param(
        type="string", enum=["r4", "stu3", "dstu2"], default="r4",
    ),
    "sync_mode": Param(
        type="string", enum=["initial", "incremental"], default="initial",
        description=(
            "`incremental` adds `_since=<last_successful_sync>` to the "
            "$export request so only modified resources are returned."
        ),
    ),
    "resource_types": Param(
        type="array",
        items={"type": "string"},
        default=[],
        description=(
            "Optional `_type=` filter (e.g. ['Patient','Condition','Observation']). "
            "Empty list = full per-patient export."
        ),
    ),
    "poll_timeout_seconds": Param(
        type="integer", default=3600, minimum=60,
        description="Max wall-clock time to wait for `$export` to complete.",
    ),
    "provenance_source": Param(
        type="string",
        enum=["PATIENT_SELF", "ADMIN_CORRECTION", "EHR_SYNC", "DOCUMENT_EXTRACTION"],
        default="EHR_SYNC",
    ),
    "provenance_source_user_id": Param(type="string", default=""),
    "provenance_target_patient_id": Param(type=["string", "null"], default=None),
    "provenance_organization_id": Param(type=["integer", "null"], default=None),
    "provenance_modification_reason": Param(type=["string", "null"], default=None),
}


@dag(
    dag_id="fhir_bulk_extract",
    max_active_runs=20,
    max_active_tasks=20,
    concurrency=100,
    params=_PARAMS,
    catchup=False,
    schedule_interval=None,
)
def _fhir_bulk_extract_dag():
    validated = validate_params.override(
        pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=300000
    )()
    artifact = bulk_extract_bundle.override(
        pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=300000
    )(validated_params=validated)
    ingest_artifact.override(
        pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=300000
    )(artifact_key=artifact, validated_params=validated)


fhir_bulk_extract = _fhir_bulk_extract_dag()
