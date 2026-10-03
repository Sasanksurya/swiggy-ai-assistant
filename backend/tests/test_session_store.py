import fakeredis.aioredis
import pytest

from app.assistant.session_store import InMemorySessionStore, RedisSessionStore
from app.assistant.state import ConversationState, Pending, Ref


def _populated(sid="s1"):
    st = ConversationState(session_id=sid)
    st.add_turn("user", "hi")
    st.last_items = [Ref(id="m-002-01", name="Masala Dosa", restaurant_id="r-002", price_inr=90)]
    st.pending = Pending(action="add_to_cart", quantity=2, candidates=st.last_items)
    return st


@pytest.fixture(params=["memory", "redis"])
def store(request):
    if request.param == "memory":
        return InMemorySessionStore()
    return RedisSessionStore(fakeredis.aioredis.FakeRedis(decode_responses=True), ttl_seconds=60)


async def test_new_session_is_empty(store):
    st = await store.get("new")
    assert st.session_id == "new" and st.history == [] and st.pending is None


async def test_roundtrip_preserves_state(store):
    await store.save(_populated())
    st = await store.get("s1")
    assert st.last_items[0].name == "Masala Dosa" and st.pending.quantity == 2
    assert st.history[0].text == "hi"


async def test_sessions_isolated_and_deletable(store):
    await store.save(_populated("a"))
    assert (await store.get("b")).last_items == []
    await store.delete("a")
    assert (await store.get("a")).last_items == []


async def test_history_is_capped():
    st = ConversationState(session_id="x")
    for i in range(50):
        st.add_turn("user", str(i))
    assert len(st.history) == 20 and st.history[-1].text == "49"


async def test_redis_sets_ttl():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await RedisSessionStore(r, ttl_seconds=60).save(_populated())
    assert 0 < await r.ttl("swiggy:session:s1") <= 60


def test_factory_builds_redis_store_without_connecting():
    from app.assistant.factory import build_store
    from app.config import Settings
    assert isinstance(build_store(Settings(_env_file=None, session_store="redis")), RedisSessionStore)
    assert isinstance(build_store(Settings(_env_file=None)), InMemorySessionStore)
