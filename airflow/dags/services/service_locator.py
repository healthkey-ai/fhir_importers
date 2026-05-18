import os

from sqlalchemy.engine import Engine

from infrastructure.airflow_client import AirflowClient, AirflowClientImplementation
from infrastructure.oauth import SmartTokenRefresher, TokenCipher
from infrastructure.postgres import create_sqlalchemy_engine
from infrastructure.repository.fhir_connection import (
    FhirConnectionRepository,
    FhirConnectionRepositoryImplementation,
)
from infrastructure.repository.institution import (
    InstitutionRepository,
    InstitutionRepositoryImplementation,
)
from infrastructure.repository.omop import (
    ConceptRepository,
    ConceptRepositoryImplementation,
    PersonRepository,
    PersonRepositoryImplementation,
    ProvenanceRepository,
    ProvenanceRepositoryImplementation,
)
from infrastructure.s3 import S3Client
from services.artifact import ArtifactService
from services.fhir_extract import FhirExtractService
from services.fhir_parsing import FhirParsingService
from services.fhir_parsing.bundle_grouper import BundleGrouper
from services.fhir_parsing.handlers.registry import build_default_registry
from services.fhir_parsing.writers import OmopWriter

# Shared with cancerbot-etl. Artifact keys are prefixed by DAG id, so the
# two repos' namespaces don't overlap (cancerbot dag ids start with `trial_*`
# / `registry_*`; healthkey dag ids start with `fhir_*`). Override per
# environment via the HEALTHKEY_ARTIFACTS_BUCKET env var if you ever want
# to split them.
_DEFAULT_ARTIFACTS_BUCKET = "cancerbot-artifacts"


class ServiceLocator:
    """Composition root for the FHIR ingestion pipeline.

    Owns every piece of environment knowledge — engine DSN, S3 bucket, etc. —
    so callers (Airflow tasks, CLI tools, tests) stay config-agnostic and
    just ask for fully-wired services.

    Construction modes:
        ServiceLocator(engine)  - caller hands in a SQLAlchemy engine.
        ServiceLocator()        - reuses class-level cache, or builds from
                                  `DATABASE_URL` via `create_sqlalchemy_engine`.

    Repositories are grouped by major entity (Person owns the per-Person
    clinical event tables + PatientInfo; Provenance owns the audit table;
    Concept stays its own concern). ConceptRepository has no concrete adapter
    yet — concept resolution (gender, LOINC, etc.) lands when the relevant
    handlers exercise it.
    """

    _engine: Engine | None = None

    def __init__(self, engine: Engine | None = None):
        if engine is not None:
            self._engine = engine
            ServiceLocator._engine = engine
            return
        if ServiceLocator._engine is not None:
            self._engine = ServiceLocator._engine
            return
        self._engine = create_sqlalchemy_engine()
        ServiceLocator._engine = self._engine

    def get_fhir_parsing_service(self) -> FhirParsingService:
        return FhirParsingService(
            artifact_service=self.get_artifact_service(),
            bundle_grouper=BundleGrouper(),
            handler_registry=build_default_registry(),
            omop_writer=self.get_omop_writer(),
        )

    def get_omop_writer(self) -> OmopWriter:
        return OmopWriter(
            person_repository=self.get_person_repository(),
            concept_repository=self.get_concept_repository(),
            provenance_repository=self.get_provenance_repository(),
        )

    @classmethod
    def get_artifact_service(cls) -> ArtifactService:
        return ArtifactService(cls.get_s3_artifacts_client())

    @staticmethod
    def get_s3_artifacts_client() -> S3Client:
        bucket = os.environ.get("HEALTHKEY_ARTIFACTS_BUCKET", _DEFAULT_ARTIFACTS_BUCKET)
        return S3Client(bucket_name=bucket)

    def get_person_repository(self) -> PersonRepository:
        return PersonRepositoryImplementation(self._engine)

    def get_provenance_repository(self) -> ProvenanceRepository:
        return ProvenanceRepositoryImplementation(self._engine)

    def get_concept_repository(self) -> ConceptRepository:
        return ConceptRepositoryImplementation(self._engine)

    # --- SMART on FHIR auth + extract -----------------------------------

    def get_fhir_connection_repository(self) -> FhirConnectionRepository:
        return FhirConnectionRepositoryImplementation(self._engine)

    def get_institution_repository(self) -> InstitutionRepository:
        return InstitutionRepositoryImplementation(self._engine)

    @staticmethod
    def get_token_cipher() -> TokenCipher:
        return TokenCipher.from_env()

    def get_smart_token_refresher(self) -> SmartTokenRefresher:
        return SmartTokenRefresher(
            connection_repository=self.get_fhir_connection_repository(),
            institution_repository=self.get_institution_repository(),
            token_cipher=self.get_token_cipher(),
        )

    def get_fhir_extract_service(self) -> FhirExtractService:
        return FhirExtractService(
            connection_repository=self.get_fhir_connection_repository(),
            institution_repository=self.get_institution_repository(),
            token_refresher=self.get_smart_token_refresher(),
            artifact_service=self.get_artifact_service(),
        )

    @staticmethod
    def get_airflow_client() -> AirflowClient:
        """Used by the `fhir_incremental_sync` scheduled DAG to fan out
        per-connection extract runs against our own Airflow instance.

        Env vars: AIRFLOW_CLIENT_URL / AIRFLOW_CLIENT_USER / AIRFLOW_CLIENT_PASSWORD.
        Same env-var names as cancerbot-etl so a shared shell profile works.
        """
        return AirflowClientImplementation(
            airflow_url=os.environ["AIRFLOW_CLIENT_URL"],
            airflow_username=os.environ["AIRFLOW_CLIENT_USER"],
            airflow_password=os.environ["AIRFLOW_CLIENT_PASSWORD"],
        )
