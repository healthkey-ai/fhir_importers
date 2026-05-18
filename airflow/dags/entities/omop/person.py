from dataclasses import dataclass
from datetime import date


@dataclass
class Person:
    """Mirrors the OMOP `person` table managed by the Django app.

    Only fields the FHIR ingestion service reads or writes are declared.
    """

    person_id: int | None = None
    gender_concept_id: int | None = None
    gender_source_value: str | None = None
    year_of_birth: int | None = None
    month_of_birth: int | None = None
    day_of_birth: int | None = None
    birth_datetime: date | None = None
    race_concept_id: int | None = None
    race_source_value: str | None = None
    ethnicity_concept_id: int | None = None
    ethnicity_source_value: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    location_id: int | None = None
