from dataclasses import dataclass, field
from typing import Any


@dataclass
class PatientInfo:
    """Denormalized per-patient summary owned by the Django app.

    The FHIR service writes a partial *patch* (free-form dict) into this row
    for fields that are not yet modelled in OMOP tables. The Django app keeps
    its own logic (signals, refresh_patient_info) that populates OMOP-derived
    fields, so the service only ships the non-OMOP delta.
    """

    id: int | None = None
    person_id: int | None = None
    organization_id: int | None = None
    patch: dict[str, Any] = field(default_factory=dict)
