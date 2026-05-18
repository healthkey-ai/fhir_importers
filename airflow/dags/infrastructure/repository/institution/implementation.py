from sqlalchemy import text
from sqlalchemy.engine import Engine

import infrastructure.repository.institution.sql as sql
from entities.fhir.institution import Institution
from infrastructure.repository.base_repository import BaseRepository
from infrastructure.repository.institution.repository import InstitutionRepository


class InstitutionRepositoryImplementation(InstitutionRepository, BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)
        self._engine = engine

    def get_by_id(self, institution_id: int) -> Institution | None:
        return self._row_to_entity(
            self._select_one(text(sql.SELECT_BY_ID), id=institution_id)
        )

    def get_by_slug(self, slug: str) -> Institution | None:
        return self._row_to_entity(
            self._select_one(text(sql.SELECT_BY_SLUG), slug=slug)
        )

    @staticmethod
    def _row_to_entity(row) -> Institution | None:
        if row is None:
            return None
        return Institution(
            id=int(row["id"]),
            slug=row["slug"],
            display_name=row["display_name"],
            fhir_base=row["fhir_base"],
            smart_config_url=row["smart_config_url"],
            client_id=row["client_id"],
            scopes=row["scopes"],
            redirect_uri=row["redirect_uri"],
            jwks_kid=row["jwks_kid"],
            supports_bulk_export=bool(row["supports_bulk_export"]),
            base_backoff_seconds=int(row["base_backoff_seconds"]),
            max_backoff_seconds=int(row["max_backoff_seconds"]),
            max_retry_count=int(row["max_retry_count"]),
            respect_retry_after=bool(row["respect_retry_after"]),
            jitter_factor=float(row["jitter_factor"]),
            retryable_status_codes=row["retryable_status_codes"] or [],
            daily_quota_reset_utc_hour=row["daily_quota_reset_utc_hour"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
