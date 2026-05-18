import os

from sqlalchemy.engine import Engine

from infrastructure.postgres import create_sqlalchemy_engine
from infrastructure.repository.omop import (
    ConceptRepository,
    PersonRepository,
    PersonRepositoryImplementation,
    ProvenanceRepository,
    ProvenanceRepositoryImplementation,
)
from infrastructure.s3 import S3Client
from services.artifact import ArtifactService
from services.fhir_parsing import FhirParsingService
from services.fhir_parsing.bundle_grouper import BundleGrouper
from services.fhir_parsing.handlers.registry import build_default_registry
from services.fhir_parsing.writers import OmopWriter

_DEFAULT_ARTIFACTS_BUCKET = "healthkey-artifacts"


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
        raise NotImplementedError(
            "ConceptRepository adapter is not yet wired. Implement "
            "infrastructure/repository/omop/concept/implementation.py and "
            "return it from ServiceLocator.get_concept_repository()."
        )
