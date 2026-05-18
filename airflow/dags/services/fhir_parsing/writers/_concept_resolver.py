"""Concept resolution cascade used by `OmopWriter`.

Mirrors the Django view's pattern: try each FHIR coding by (system→vocab, code),
fall back to a fuzzy name lookup against the OMOP `concept` table, fall back
to a hard-coded generic concept appropriate for the resource type.
"""
from __future__ import annotations

import logging
from enum import IntEnum
from typing import Iterable

from entities.omop.concept import Concept
from infrastructure.repository.omop import ConceptRepository
from services.fhir_parsing.codesystems import detect_vocabulary
from services.fhir_parsing.fhir_parsing_types import Coding

_logger = logging.getLogger(__name__)


class GenericConcept(IntEnum):
    """Logical fallback concepts. The resolver tries each `*_OPTIONS` chain
    in order, returning the first id that actually exists in the OMOP
    `concept` table — this makes the writer work on both a full-OMOP-vocab
    deployment AND on the cancer-research dev DB (which uses HealthTree-style
    SNOMED ids for the type columns)."""

    # Primary names are the OMOP-standard ids (used by the Django view and
    # full-OMOP-vocabulary deployments).
    LAB_TEST = 3000963
    EHR_VISIT_TYPE = 32817
    LAB_TYPE = 32856
    EHR_DRUG_TYPE = 32869
    GENDER_MALE = 8507
    GENDER_FEMALE = 8532
    GENDER_UNKNOWN = 8551


# Fallback chains for sparse-vocab deployments. The cancer-research dev DB
# has 37 concepts and uses SNOMED ids for "type" columns.
_FALLBACK_CHAINS: dict[int, tuple[int, ...]] = {
    GenericConcept.EHR_VISIT_TYPE: (GenericConcept.EHR_VISIT_TYPE, 44818517),  # SNOMED 'EHR record'
    GenericConcept.LAB_TYPE: (GenericConcept.LAB_TYPE, 44818702),              # SNOMED 'Lab result'
    GenericConcept.EHR_DRUG_TYPE: (GenericConcept.EHR_DRUG_TYPE, 38000177),    # SNOMED 'Prescription written'
    GenericConcept.LAB_TEST: (GenericConcept.LAB_TEST, 44818702),              # share with LAB_TYPE
}


_GENDER_CONCEPT_BY_SOURCE: dict[str, int] = {
    "male": GenericConcept.GENDER_MALE,
    "female": GenericConcept.GENDER_FEMALE,
    "m": GenericConcept.GENDER_MALE,
    "f": GenericConcept.GENDER_FEMALE,
}


class ConceptResolver:
    """Stateful helper that resolves Codings to OMOP concept_ids.

    The repository already memoizes per-(code, vocab) lookups; this class
    just orchestrates the cascade. Callers pass the codings, an optional
    fuzzy-text fallback (FHIR `code.text`), and a generic fallback concept_id.
    """

    def __init__(self, concept_repository: ConceptRepository):
        self._repository = concept_repository

    def resolve(
        self,
        codings: Iterable[Coding],
        fuzzy_text: str | None = None,
        fallback: int | None = None,
    ) -> int | None:
        # Direct (system, code) lookups first.
        for coding in codings:
            if not coding.code:
                continue
            vocab = detect_vocabulary({"system": coding.system, "code": coding.code})
            if vocab is None:
                continue
            concept = self._repository.find_by_code(str(coding.code), str(vocab.value))
            if concept is not None:
                return concept.concept_id
        # Fuzzy name lookup (legacy `textMappingSearch` equivalent).
        if fuzzy_text:
            concept = self._repository.find_by_name(fuzzy_text)
            if concept is not None:
                return concept.concept_id
        # Generic fallback. Walk a configured chain so deployments with
        # sparse vocabularies (no 3000963 etc.) can pick the SNOMED equivalent.
        if fallback is not None:
            for candidate in _FALLBACK_CHAINS.get(fallback, (fallback,)):
                generic = self._repository.get_by_id(candidate)
                if generic is not None:
                    return generic.concept_id
            _logger.warning(
                "No fallback concept in chain for %d present in `concept`; row will be skipped",
                fallback,
            )
        return None

    def resolve_gender(self, source_value: str | None) -> int | None:
        if not source_value:
            return None
        return _GENDER_CONCEPT_BY_SOURCE.get(source_value.strip().lower())

    def get_type_concept(self, fallback: int) -> int | None:
        """For *_type_concept_id columns. Walks the fallback chain so the
        writer works on sparsely-loaded `concept` tables."""
        for candidate in _FALLBACK_CHAINS.get(fallback, (fallback,)):
            concept = self._repository.get_by_id(candidate)
            if concept is not None:
                return concept.concept_id
        return None
