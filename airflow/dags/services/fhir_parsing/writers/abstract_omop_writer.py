import abc

from services.fhir_parsing.fhir_parsing_types import (
    FhirPatientIngestionResult,
    ParsedPatientPayload,
    ProvenanceContext,
)


class AbstractOmopWriter(abc.ABC):
    """Port that turns a ParsedPatientPayload into OMOP rows.

    Kept abstract so tests can substitute an in-memory writer and the service
    orchestrator stays unaware of how persistence is implemented.
    """

    @abc.abstractmethod
    def write_patient(
        self,
        payload: ParsedPatientPayload,
        provenance: ProvenanceContext,
    ) -> FhirPatientIngestionResult:
        raise NotImplementedError
