from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass
class DrugExposure:
    drug_exposure_id: int | None = None
    person_id: int | None = None
    drug_concept_id: int | None = None
    drug_exposure_start_date: date | None = None
    drug_exposure_start_datetime: datetime | None = None
    drug_exposure_end_date: date | None = None
    drug_exposure_end_datetime: datetime | None = None
    drug_type_concept_id: int | None = None
    stop_reason: str | None = None
    quantity: Decimal | float | None = None
    days_supply: int | None = None
    sig: str | None = None
    route_concept_id: int | None = None
    drug_source_value: str | None = None
    route_source_value: str | None = None
    dose_unit_source_value: str | None = None
