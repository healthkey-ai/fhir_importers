from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class ProcedureOccurrence:
    procedure_occurrence_id: int | None = None
    person_id: int | None = None
    procedure_concept_id: int | None = None
    procedure_date: date | None = None
    procedure_datetime: datetime | None = None
    procedure_end_date: date | None = None
    procedure_end_datetime: datetime | None = None
    procedure_type_concept_id: int | None = None
    quantity: int | None = None
    procedure_source_value: str | None = None
    modifier_source_value: str | None = None
