"""Tests for the DB-backed PKCE state store."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.epic.models import EpicAuthState
from apps.epic.state_store import DbStateStore, PendingState


def _pending(alias="my_chart_central"):
    return PendingState(
        code_verifier="verifier",
        token_endpoint="https://token.example/oauth2/token",
        organization_alias=alias,
    )


@pytest.mark.django_db
def test_put_then_pop_returns_value_once():
    store = DbStateStore(ttl_seconds=600)
    store.put("s1", _pending())

    got = store.pop("s1")
    assert got is not None
    assert got.code_verifier == "verifier"
    assert got.organization_alias == "my_chart_central"

    # Consumed exactly once — a second pop finds nothing.
    assert store.pop("s1") is None
    assert not EpicAuthState.objects.filter(pk="s1").exists()


@pytest.mark.django_db
def test_pop_unknown_state_returns_none():
    assert DbStateStore(ttl_seconds=600).pop("nope") is None


@pytest.mark.django_db
def test_expired_state_is_dropped():
    store = DbStateStore(ttl_seconds=600)
    store.put("old", _pending())
    # Force expiry.
    EpicAuthState.objects.filter(pk="old").update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert store.pop("old") is None  # expired → None, and consumed
    assert not EpicAuthState.objects.filter(pk="old").exists()


@pytest.mark.django_db
def test_put_purges_expired_rows():
    store = DbStateStore(ttl_seconds=600)
    EpicAuthState.objects.create(
        state="stale", code_verifier="v", token_endpoint="https://t.example",
        organization_alias="x", expires_at=timezone.now() - timedelta(minutes=1),
    )
    store.put("fresh", _pending())  # write triggers GC of expired rows
    assert not EpicAuthState.objects.filter(pk="stale").exists()
    assert EpicAuthState.objects.filter(pk="fresh").exists()
