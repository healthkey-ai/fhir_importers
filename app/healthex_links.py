import abc
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import HealthExLink


# Status values — kept as plain strings so the DB column can evolve without
# enum migrations. New values added on either end must be added to the docstring
# on HealthExLink.status.
STATUS_PENDING_CONSENT = "PENDING_CONSENT"
STATUS_RETRIEVAL_IN_PROGRESS = "RETRIEVAL_IN_PROGRESS"
STATUS_COMPLETE = "COMPLETE"
STATUS_ERROR = "ERROR"
STATUS_REVOKED = "REVOKED"


@dataclass
class HealthExLinkMetadata:
    project_id: str
    external_id: str
    healthex_patient_id: str | None
    status: str
    onboarding_url: str | None
    consented_at: datetime | None
    last_status_polled_at: datetime | None
    last_synced_at: datetime | None
    connected_at: datetime


class BaseHealthExLinksRepository(abc.ABC):
    """Persistence for a user's HealthEx Project enrollments."""

    @abc.abstractmethod
    async def upsert(
        self,
        *,
        user_uid: str,
        project_id: str,
        external_id: str,
        healthex_patient_id: str | None,
        status: str,
        onboarding_url: str | None,
    ) -> HealthExLinkMetadata: ...

    @abc.abstractmethod
    async def get(
        self, user_uid: str, project_id: str,
    ) -> HealthExLinkMetadata | None: ...

    @abc.abstractmethod
    async def list_for_user(self, user_uid: str) -> list[HealthExLinkMetadata]: ...

    @abc.abstractmethod
    async def delete(self, user_uid: str, project_id: str) -> bool: ...

    @abc.abstractmethod
    async def update_status(
        self,
        *,
        user_uid: str,
        project_id: str,
        status: str,
        healthex_patient_id: str | None = None,
        polled_at: datetime | None = None,
        consented_at: datetime | None = None,
        synced_at: datetime | None = None,
    ) -> HealthExLinkMetadata | None: ...


class HealthExLinksRepository(BaseHealthExLinksRepository):
    """Postgres-backed implementation via SQLModel."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert(
        self,
        *,
        user_uid: str,
        project_id: str,
        external_id: str,
        healthex_patient_id: str | None,
        status: str,
        onboarding_url: str | None,
    ) -> HealthExLinkMetadata:
        now = datetime.now(timezone.utc)
        existing = await self._fetch(user_uid, project_id)

        if existing is None:
            link = HealthExLink(
                user_uid=user_uid,
                project_id=project_id,
                external_id=external_id,
                healthex_patient_id=healthex_patient_id,
                status=status,
                onboarding_url=onboarding_url,
                created_at=now,
                updated_at=now,
            )
            self._session.add(link)
        else:
            existing.external_id = external_id
            if healthex_patient_id is not None:
                existing.healthex_patient_id = healthex_patient_id
            existing.status = status
            if onboarding_url is not None:
                existing.onboarding_url = onboarding_url
            existing.updated_at = now
            link = existing

        await self._session.commit()
        await self._session.refresh(link)
        return _to_metadata(link)

    async def get(
        self, user_uid: str, project_id: str,
    ) -> HealthExLinkMetadata | None:
        link = await self._fetch(user_uid, project_id)
        return _to_metadata(link) if link else None

    async def list_for_user(self, user_uid: str) -> list[HealthExLinkMetadata]:
        rows = (
            await self._session.execute(
                select(HealthExLink).where(HealthExLink.user_uid == user_uid)
            )
        ).scalars().all()
        return [_to_metadata(r) for r in rows]

    async def delete(self, user_uid: str, project_id: str) -> bool:
        link = await self._fetch(user_uid, project_id)
        if link is None:
            return False
        await self._session.delete(link)
        await self._session.commit()
        return True

    async def update_status(
        self,
        *,
        user_uid: str,
        project_id: str,
        status: str,
        healthex_patient_id: str | None = None,
        polled_at: datetime | None = None,
        consented_at: datetime | None = None,
        synced_at: datetime | None = None,
    ) -> HealthExLinkMetadata | None:
        link = await self._fetch(user_uid, project_id)
        if link is None:
            return None
        link.status = status
        if healthex_patient_id is not None:
            link.healthex_patient_id = healthex_patient_id
        if polled_at is not None:
            link.last_status_polled_at = polled_at
        if consented_at is not None and link.consented_at is None:
            link.consented_at = consented_at
        if synced_at is not None:
            link.last_synced_at = synced_at
        link.updated_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._session.refresh(link)
        return _to_metadata(link)

    async def _fetch(
        self, user_uid: str, project_id: str,
    ) -> HealthExLink | None:
        return (
            await self._session.execute(
                select(HealthExLink).where(
                    HealthExLink.user_uid == user_uid,
                    HealthExLink.project_id == project_id,
                )
            )
        ).scalar_one_or_none()


def _to_metadata(link: HealthExLink) -> HealthExLinkMetadata:
    return HealthExLinkMetadata(
        project_id=link.project_id,
        external_id=link.external_id,
        healthex_patient_id=link.healthex_patient_id,
        status=link.status,
        onboarding_url=link.onboarding_url,
        consented_at=link.consented_at,
        last_status_polled_at=link.last_status_polled_at,
        last_synced_at=link.last_synced_at,
        connected_at=link.created_at,
    )
