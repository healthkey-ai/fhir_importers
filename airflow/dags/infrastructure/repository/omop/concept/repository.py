import abc

from entities.omop.concept import Concept


class ConceptRepository(abc.ABC):
    """Port for the OMOP `concept` table. Read-only for ingestion.

    Used by writers/handlers to resolve FHIR code systems (LOINC, SNOMED,
    RxNorm) and OMOP-internal lookups (gender, EHR type, Lab type) into
    `concept_id` values.
    """

    @abc.abstractmethod
    def get_by_id(self, concept_id: int) -> Concept | None:
        raise NotImplementedError

    @abc.abstractmethod
    def find_by_code(self, code: str, vocabulary_id: str) -> Concept | None:
        """e.g. find_by_code('718-7', 'LOINC') -> haemoglobin concept."""
        raise NotImplementedError

    @abc.abstractmethod
    def find_by_name(self, name_substring: str) -> Concept | None:
        raise NotImplementedError
