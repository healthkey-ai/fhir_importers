import abc
from contextlib import AbstractContextManager
from datetime import datetime

from entities.fhir.connection import FhirConnection


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
        """Mark all connections for `institution_id` (or matching some other
        criteria the caller supplies) as `needs_reauth`. Used when a refresh
        attempt returns `invalid_grant`."""
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
