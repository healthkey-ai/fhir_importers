from datetime import datetime, timedelta, timezone

from app.connections import BaseConnectionsRepository

from .fakes import InMemoryConnectionsRepository


def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


def test_in_memory_is_base_subclass():
    assert issubclass(InMemoryConnectionsRepository, BaseConnectionsRepository)


async def test_upsert_then_list_returns_one_row():
    repo = InMemoryConnectionsRepository()
    await repo.upsert(
        user_uid="u1",
        organization_alias="alpha",
        access_token="AT",
        refresh_token="RT",
        id_token=None,
        scope="patient/*.read",
        patient="P-1",
        expires_at=_future(),
    )
    rows = await repo.list_for_user("u1")
    assert len(rows) == 1
    assert rows[0].organization_alias == "alpha"
    assert rows[0].patient == "P-1"
    assert rows[0].scope == "patient/*.read"


async def test_two_users_are_isolated():
    repo = InMemoryConnectionsRepository()
    await repo.upsert(
        user_uid="u1",
        organization_alias="alpha",
        access_token="A",
        refresh_token=None,
        id_token=None,
        scope=None,
        patient=None,
        expires_at=_future(),
    )
    await repo.upsert(
        user_uid="u2",
        organization_alias="alpha",
        access_token="B",
        refresh_token=None,
        id_token=None,
        scope=None,
        patient=None,
        expires_at=_future(),
    )
    assert len(await repo.list_for_user("u1")) == 1
    assert len(await repo.list_for_user("u2")) == 1


async def test_upsert_twice_keeps_one_row_and_preserves_connected_at():
    repo = InMemoryConnectionsRepository()
    first = await repo.upsert(
        user_uid="u1",
        organization_alias="alpha",
        access_token="A1",
        refresh_token=None,
        id_token=None,
        scope=None,
        patient=None,
        expires_at=_future(),
    )
    second = await repo.upsert(
        user_uid="u1",
        organization_alias="alpha",
        access_token="A2",
        refresh_token="R2",
        id_token=None,
        scope="new-scope",
        patient="new-patient",
        expires_at=_future(),
    )
    rows = await repo.list_for_user("u1")
    assert len(rows) == 1
    assert second.connected_at == first.connected_at  # original timestamp survives
    assert rows[0].scope == "new-scope"
    assert rows[0].patient == "new-patient"


async def test_delete_existing_returns_true_and_removes():
    repo = InMemoryConnectionsRepository()
    await repo.upsert(
        user_uid="u1",
        organization_alias="alpha",
        access_token="A",
        refresh_token=None,
        id_token=None,
        scope=None,
        patient=None,
        expires_at=_future(),
    )
    assert await repo.delete("u1", "alpha") is True
    assert await repo.list_for_user("u1") == []


async def test_delete_missing_returns_false():
    repo = InMemoryConnectionsRepository()
    assert await repo.delete("u1", "alpha") is False


async def test_delete_other_users_connection_returns_false():
    repo = InMemoryConnectionsRepository()
    await repo.upsert(
        user_uid="u1",
        organization_alias="alpha",
        access_token="A",
        refresh_token=None,
        id_token=None,
        scope=None,
        patient=None,
        expires_at=_future(),
    )
    # u2 cannot delete u1's connection — must return False, u1's row stays.
    assert await repo.delete("u2", "alpha") is False
    assert len(await repo.list_for_user("u1")) == 1
