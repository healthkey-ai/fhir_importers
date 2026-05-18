import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

import infrastructure.repository.omop.provenance.sql as sql
from entities.omop.provenance_record import ProvenanceRecord
from infrastructure.repository.base_repository import BaseRepository
from infrastructure.repository.omop.provenance.repository import ProvenanceRepository

_logger = logging.getLogger(__name__)


class ProvenanceRepositoryImplementation(ProvenanceRepository, BaseRepository):
    """Raw SQL adapter against `provenance_record`.

    Caches the (app_label, model) → content_type_id lookup in-process; the
    `django_content_type` table is small, static, and read in a hot loop
    (every clinical row gets a provenance record).
    """

    def __init__(self, engine: Engine):
        super().__init__(engine)
        self._engine = engine
        self._content_type_cache: dict[tuple[str, str], int] = {}

    def create(self, record: ProvenanceRecord) -> ProvenanceRecord:
        assert record.source is not None, "ProvenanceRecord.source is required"
        assert record.app_label and record.model, (
            "ProvenanceRecord must carry (app_label, model) so the repository "
            "can resolve content_type_id"
        )
        assert record.object_id is not None, "ProvenanceRecord.object_id is required"

        content_type_id = self._resolve_content_type_id(record.app_label, record.model)
        record_id = self._execute_and_scalar_one(
            text(sql.INSERT_PROVENANCE_RECORD),
            source=record.source.value,
            source_user_id=record.source_user_id or "",
            target_patient_id=record.target_patient_id,
            modification_reason=record.modification_reason,
            organization_id=record.organization_id,
            content_type_id=content_type_id,
            object_id=record.object_id,
        )
        record.id = int(record_id)
        return record

    def _resolve_content_type_id(self, app_label: str, model: str) -> int:
        key = (app_label, model)
        cached = self._content_type_cache.get(key)
        if cached is not None:
            return cached
        row = self._select_one(
            text(sql.SELECT_CONTENT_TYPE_ID),
            app_label=app_label,
            model=model,
        )
        if row is None:
            raise LookupError(
                f"No django_content_type row for ({app_label!r}, {model!r}). "
                f"Has the Django app run migrations against this DB?"
            )
        self._content_type_cache[key] = int(row["id"])
        return self._content_type_cache[key]
