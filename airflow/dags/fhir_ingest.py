import logging

from airflow.decorators import dag
from airflow.models.param import Param

from infrastructure.airflow_db.consts import AIRFLOW_POOL_GREAT_BACKGROUND
from tasks.fhir_ingest_tasks import ingest_bundle, validate_params

_logger = logging.getLogger(__name__)


_PARAMS = {
    # Bundle source: caller supplies exactly one of `artifact_key` (S3 path)
    # or `bundle` (inline JSON). The Django `upload_fhir` endpoint passes the
    # bundle inline; future bulk-upload flows would stage to S3 first.
    "artifact_key": Param(
        type=["string", "null"],
        default=None,
        description=(
            "S3 key (within the artifacts bucket) of a staged FHIR Bundle JSON. "
            "Mutually exclusive with `bundle`."
        ),
    ),
    "bundle": Param(
        type=["object", "null"],
        default=None,
        description=(
            "Inline FHIR Bundle JSON. Use when the bundle is small enough to fit "
            "in Airflow's `dag_run.conf` (jsonb). Mutually exclusive with `artifact_key`."
        ),
    ),
    "fhir_version": Param(
        type="string",
        enum=["r4", "stu3", "dstu2"],
        default="r4",
        description=(
            "FHIR version of the staged Bundle. Dispatches to the matching "
            "per-resource handlers under services/fhir_parsing/handlers/<version>/."
        ),
    ),
    "provenance_source": Param(
        type=["string", "null"],
        default=None,
        enum=[None, "PATIENT_SELF", "ADMIN_CORRECTION", "EHR_SYNC", "DOCUMENT_EXTRACTION"],
        description="`provenance_record.source` value. Stamped on every OMOP row the run touches.",
    ),
    "provenance_source_user_id": Param(
        type="string",
        default="",
        description="`provenance_record.source_user_id` — operator id (string) for the audit trail.",
    ),
    "provenance_target_patient_id": Param(
        type=["string", "null"],
        default=None,
        description=(
            "`provenance_record.target_patient_id` — external patient id for analytics filtering. "
            "Optional; defaults to null."
        ),
    ),
    "provenance_organization_id": Param(
        type=["integer", "null"],
        default=None,
        description=(
            "Organization id derived from the OAuth2 token. Scopes ingested "
            "rows (e.g. `patient_info.organization`) to a tenant."
        ),
    ),
    "provenance_modification_reason": Param(
        type=["string", "null"],
        default=None,
        description=(
            "Required when `provenance_source = ADMIN_CORRECTION`. Free-text "
            "rationale for the audit trail."
        ),
    ),
}


@dag(
    dag_id="fhir_ingest",
    max_active_runs=20,
    max_active_tasks=20,
    concurrency=100,
    params=_PARAMS,
    catchup=False,
    schedule_interval=None,
)
def _fhir_ingest_dag():
    validated = validate_params.override(
        pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=300000
    )()
    ingest_bundle.override(
        pool=AIRFLOW_POOL_GREAT_BACKGROUND, priority_weight=300000
    )(validated_params=validated)


fhir_ingest = _fhir_ingest_dag()
