from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .crypto import TokenCipher
from .models import MyChartConnection


@dataclass
class ConnectionMetadata:
    organization_alias: str
    patient: str | None
    scope: str | None
    expires_at: datetime
    connected_at: datetime


class ConnectionsRepository:
    def __init__(self, session: AsyncSession, cipher: TokenCipher):
        self._session = session
        self._cipher = cipher

    async def upsert(
        self,
        *,
        user_uid: str,
        organization_alias: str,
        access_token: str,
        refresh_token: str | None,
        id_token: str | None,
        scope: str | None,
        patient: str | None,
        expires_at: datetime,
    ) -> MyChartConnection:
        now = datetime.now(timezone.utc)
        existing = (
            await self._session.execute(
                select(MyChartConnection).where(
                    MyChartConnection.user_uid == user_uid,
                    MyChartConnection.organization_alias == organization_alias,
                )
            )
        ).scalar_one_or_none()

        enc_access = self._cipher.encrypt(access_token)
        enc_refresh = self._cipher.encrypt(refresh_token) if refresh_token else None
        enc_id = self._cipher.encrypt(id_token) if id_token else None

        if existing is None:
            conn = MyChartConnection(
                user_uid=user_uid,
                organization_alias=organization_alias,
                access_token=enc_access,
                refresh_token=enc_refresh,
                id_token=enc_id,
                scope=scope,
                patient=patient,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            self._session.add(conn)
        else:
            existing.access_token = enc_access
            existing.refresh_token = enc_refresh
            existing.id_token = enc_id
            existing.scope = scope
            existing.patient = patient
            existing.expires_at = expires_at
            existing.updated_at = now
            conn = existing

        await self._session.commit()
        await self._session.refresh(conn)
        return conn

    async def delete(self, user_uid: str, organization_alias: str) -> bool:
        existing = (
            await self._session.execute(
                select(MyChartConnection).where(
                    MyChartConnection.user_uid == user_uid,
                    MyChartConnection.organization_alias == organization_alias,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            return False
        await self._session.delete(existing)
        await self._session.commit()
        return True

    async def list_for_user(self, user_uid: str) -> list[ConnectionMetadata]:
        rows = (
            await self._session.execute(
                select(MyChartConnection).where(MyChartConnection.user_uid == user_uid)
            )
        ).scalars().all()
        return [
            ConnectionMetadata(
                organization_alias=r.organization_alias,
                patient=r.patient,
                scope=r.scope,
                expires_at=r.expires_at,
                connected_at=r.created_at,
            )
            for r in rows
        ]
