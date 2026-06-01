from app.state_store import BaseStateStore, PendingState

from .fakes import InMemoryStateStore


def test_in_memory_is_base_subclass():
    assert issubclass(InMemoryStateStore, BaseStateStore)


async def test_put_then_pop_returns_value():
    store = InMemoryStateStore()
    state = "st-1"
    pending = PendingState(
        code_verifier="cv",
        token_endpoint="https://x/token",
        organization_alias="example_hospital",
    )
    await store.put(state, pending)
    assert await store.pop(state) == pending


async def test_pop_consumes_state():
    store = InMemoryStateStore()
    await store.put(
        "st-2",
        PendingState(code_verifier="cv", token_endpoint="https://x", organization_alias="a"),
    )
    assert await store.pop("st-2") is not None
    # Second pop must not return the same value — state is single-use.
    assert await store.pop("st-2") is None


async def test_pop_unknown_state_returns_none():
    store = InMemoryStateStore()
    assert await store.pop("never-stored") is None
