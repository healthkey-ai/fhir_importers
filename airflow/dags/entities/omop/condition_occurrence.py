from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class ConditionOccurrence:
    condition_occurrence_id: int | None = None
    person_id: int | None = None
    condition_concept_id: int | None = None
    condition_start_date: date | None = None
    condition_start_datetime: datetime | None = None
    condition_end_date: date | None = None
    condition_type_concept_id: int | None = None
    condition_source_value: str | None = None
    condition_status_source_value: str | None = None
