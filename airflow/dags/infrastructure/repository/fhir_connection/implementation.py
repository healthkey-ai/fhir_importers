"""SQLAlchemy implementation of FhirConnectionRepository.

The interesting bit is `lock_for_update`: it opens a transaction, holds a
row-level lock for the duration of the `with` block, and lets the caller
issue follow-up `update_tokens()` calls inside that same transaction so
the lock is meaningful. On exit, the transaction commits (or rolls back
if an exception bubbles).
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

import infrastructure.repository.fhir_connection.sql as sql
from entities.fhir.connection import FhirConnection, FhirConnectionStatus
from infrastructure.repository.base_repository import BaseRepository
from infrastructure.repository.fhir_connection.repository import FhirConnectionRepository

_logger = logging.getLogger(__name__)


class FhirConnectionRepositoryImplementation(FhirConnectionRepository, BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)
        self._engine = engine
        # Used inside a `lock_for_update` block to expose the live connection
        # to `update_tokens`. Set per-call; cleared on context exit.
        self._active_conn: Connection | None = None

    # ---- reads ----------------------------------------------------------

    def get_by_id(self, connection_id: int) -> FhirConnection | None:
        row = self._select_one(text(sql.SELECT_BY_ID), id=connection_id)
        return _row_to_entity(row)

    # ---- locked read + write -------------------------------------------

    @contextmanager
    def lock_for_update(self, connection_id: int) -> Iterator[FhirConnection]:
        with self._engine.begin() as conn:
            row = conn.execute(text(sql.SELECT_FOR_UPDATE), {"id": connection_id}).fetchone()
            if row is None:
                raise LookupError(f"fhir_connection id={connection_id} not found")
            entity = _row_to_entity(dict(row._mapping))
            self._active_conn = conn
            try:
                yield entity
            finally:
                self._active_conn = None

    def update_tokens(self, connection: FhirConnection) -> None:
        if self._active_conn is None:
            raise RuntimeError(
                "update_tokens() must be called inside a lock_for_update() block"
            )
        self._active_conn.execute(
            text(sql.UPDATE_TOKENS),
            {
                "id": connection.id,
                "access_token_encrypted": connection.access_token_encrypted,
                "refresh_token_encrypted": connection.refresh_token_encrypted,
                "expires_at": connection.expires_at,
                "status": connection.status.value,
                "last_token_refresh_at": connection.last_token_refresh_at,
                "last_error": connection.last_error or "",
            },
        )

    # ---- standalone writes ---------------------------------------------

    def mark_needs_reauth(self, institution_id: int, *, reason: str) -> None:
        self._execute(
            text(sql.MARK_NEEDS_REAUTH),
            institution_id=institution_id,
            reason=reason[:500],
        )

    def record_sync_attempt(
        self,
        connection_id: int,
        *,
        succeeded: bool,
        attempted_at: datetime,
        error: str = "",
    ) -> None:
        if succeeded:
            self._execute(
                text(sql.RECORD_SYNC_SUCCESS),
                id=connection_id,
                attempted_at=attempted_at,
            )
        else:
            self._execute(
                text(sql.RECORD_SYNC_FAILURE),
                id=connection_id,
                attempted_at=attempted_at,
                error=error[:2000],
            )


def _row_to_entity(row) -> FhirConnection | None:
    if row is None:
        return None
    return FhirConnection(
        id=int(row["id"]),
        person_id=row["person_id"],
        institution_id=row["institution_id"],
        organization_id=row["organization_id"],
        access_token_encrypted=row["access_token_encrypted"],
        refresh_token_encrypted=row["refresh_token_encrypted"],
        expires_at=row["expires_at"],
        scope_granted=row["scope_granted"] or "",
        fhir_patient_id=row["fhir_patient_id"],
        status=FhirConnectionStatus(row["status"]),
        last_successful_sync=row["last_successful_sync"],
        last_attempted_sync=row["last_attempted_sync"],
        last_token_refresh_at=row["last_token_refresh_at"],
        failure_count=int(row["failure_count"]),
        last_error=row["last_error"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
