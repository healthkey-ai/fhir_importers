import abc
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime

from entities.fhir.connection import FhirConnection


@dataclass
class DueConnectionRow:
    """Projection returned by `list_due_for_sync` — flat row, not the full
    FhirConnection entity. The scheduler only needs a handful of fields to
    fan out per-connection extract runs.
    """

    connection_id: int
    institution_id: int
    institution_slug: str
    supports_bulk_export: bool
    last_successful_sync: datetime | None


class FhirConnectionRepository(abc.ABC):
    """Port for the Django-owned `fhir_connection` table.

    The Airflow side reads + writes connections (specifically: refreshes
    tokens). Django writes the initial row on OAuth callback. Concurrent
    refreshers serialise on a row-level lock via `lock_for_update`.
    """

    @abc.abstractmethod
    def get_by_id(self, connection_id: int) -> FhirConnection | None:
        raise NotImplementedError

    @abc.abstractmethod
    def lock_for_update(self, connection_id: int) -> AbstractContextManager[FhirConnection]:
        """Acquire a row-level lock on the connection for the duration of
        the context. Inside the `with` block, callers may call
        `update_tokens(...)`. The lock releases on context exit (commit)."""
        raise NotImplementedError

    @abc.abstractmethod
    def update_tokens(self, connection: FhirConnection) -> None:
        """Persist the token + status + watermark fields of a connection
        that was loaded via `lock_for_update`. Must be called inside the
        same context that issued the lock."""
        raise NotImplementedError

    @abc.abstractmethod
    def mark_needs_reauth(self, institution_id: int, *, reason: str) -> None:
        """Mark connections for `institution_id` as `needs_reauth`. Used
        when a refresh attempt returns `invalid_grant`."""
        raise NotImplementedError

    @abc.abstractmethod
    def record_sync_attempt(
        self,
        connection_id: int,
        *,
        succeeded: bool,
        attempted_at: datetime,
        error: str = "",
    ) -> None:
        """Update last_attempted_sync (+ last_successful_sync and reset
        failure_count on success, or bump failure_count on failure)."""
        raise NotImplementedError

    @abc.abstractmethod
    def flag_expiring_tokens(self, *, days_until_expiry: int) -> int:
        """Bump `connected` rows whose access_token expires within
        `days_until_expiry` to `expiring_soon`. Used by the token-monitor
        scheduled DAG. Returns the count of rows updated."""
        raise NotImplementedError

    @abc.abstractmethod
    def list_due_for_sync(
        self,
        *,
        min_age_hours: int,
        limit: int = 1000,
    ) -> list[DueConnectionRow]:
        """Connections due for an incremental sync.

        Definition of "due":
          - `last_successful_sync` is older than `min_age_hours` (or NULL).
          - `status` is in (connected, expiring_soon) — excludes revoked,
            needs_reauth, degraded.
          - Joined with `fhir_institution` so the scheduler knows whether
            to target fhir_extract or fhir_bulk_extract per row.
        """
        raise NotImplementedError
