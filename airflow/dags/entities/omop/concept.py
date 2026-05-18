from dataclasses import dataclass


@dataclass
class Concept:
    """Mirrors the OMOP `concept` table. Read-only for the FHIR ingestion service."""

    concept_id: int
    concept_name: str | None = None
    concept_code: str | None = None
    vocabulary_id: str | None = None
