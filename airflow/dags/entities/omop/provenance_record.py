from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ProvenanceSource(StrEnum):
    """Enum values must match `provenance_record.source` in the Django app
    (see ProvenanceRecord.SOURCE_CHOICES in ctomop/omop_core/models.py)."""

    PATIENT_SELF = "PATIENT_SELF"
    ADMIN_CORRECTION = "ADMIN_CORRECTION"
    EHR_SYNC = "EHR_SYNC"
    DOCUMENT_EXTRACTION = "DOCUMENT_EXTRACTION"


@dataclass
class ProvenanceRecord:
    """Mirrors the `provenance_record` table.

    The Django app uses a generic foreign key: `content_type_id` joins to
    `django_content_type(id)` and `object_id` is the PK of whatever model
    the record refers to. The ETL writes those two columns directly; the
    repository resolves `content_type_id` from a (`app_label`, `model`)
    tuple.
    """

    id: int | None = None
    source: ProvenanceSource | None = None
    source_user_id: str = ""
    target_patient_id: str | None = None
    modification_reason: str | None = None
    organization_id: int | None = None
    app_label: str | None = None
    model: str | None = None
    object_id: int | None = None
    created_at: datetime | None = None
