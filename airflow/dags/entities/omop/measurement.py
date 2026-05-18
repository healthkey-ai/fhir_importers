from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass
class Measurement:
    measurement_id: int | None = None
    person_id: int | None = None
    measurement_concept_id: int | None = None
    measurement_date: date | None = None
    measurement_datetime: datetime | None = None
    measurement_time: str | None = None
    measurement_type_concept_id: int | None = None
    operator_concept_id: int | None = None
    value_as_number: Decimal | float | None = None
    value_as_string: str | None = None
    value_as_concept_id: int | None = None
    unit_concept_id: int | None = None
    measurement_source_value: str | None = None
    unit_source_value: str | None = None
    value_source_value: str | None = None
