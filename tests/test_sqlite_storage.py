import pytest

from marznode.models import Inbound, Outbound, User
from marznode.storage.sqlite import SqliteStorage


async def _close(storage: SqliteStorage) -> None:
    if storage._db is not None:
        await storage._db.close()
        storage._db = None


@pytest.mark.asyncio
async def test_sqlite_storage_round_trips_inbounds_and_outbounds(tmp_path):
    db_path = str(tmp_path / "marznode.db")
    base_inbound = Inbound(
        tag="base-in",
        protocol="vless",
        config={"port": 443},
    )
    res_inbound = Inbound(
        tag="res-in",
        protocol="trojan",
        config={"port": 8443},
    )
    outbounds = [
        Outbound(
            protocol="socks",
            address="198.51.100.10",
            port=1080,
            username="alice-up",
            password="secret",
            inbound_tags=["res-in"],
        ),
        Outbound(
            protocol="http",
            address="203.0.113.20",
            port=8080,
            inbound_tags=["base-in", "res-in"],
        ),
    ]

    storage = SqliteStorage(db_path)
    storage.register_inbound(base_inbound)
    storage.register_inbound(res_inbound)
    user = User(id=7, username="alice", key="k-alice")
    await storage.update_user_inbounds(user, [base_inbound, res_inbound])
    await storage.update_user_outbounds(user, outbounds)
    await _close(storage)

    reopened = SqliteStorage(db_path)
    reopened.register_inbound(base_inbound)
    reopened.register_inbound(res_inbound)
    restored = await reopened.list_users(7)

    assert restored.username == "alice"
    assert {inbound.tag for inbound in restored.inbounds} == {"base-in", "res-in"}
    assert [outbound.model_dump() for outbound in restored.outbounds] == [
        outbound.model_dump() for outbound in outbounds
    ]

    await reopened.update_user_outbounds(restored, [])
    assert await reopened.list_user_outbounds(7) == []
    cleared = await reopened.list_users(7)
    assert cleared.outbounds == []
    await _close(reopened)


@pytest.mark.asyncio
async def test_sqlite_remove_user_cascades_outbounds(tmp_path):
    storage = SqliteStorage(str(tmp_path / "marznode.db"))
    inbound = Inbound(tag="res-in", protocol="trojan", config={"port": 8443})
    storage.register_inbound(inbound)
    user = User(id=9, username="bob", key="k-bob")
    await storage.update_user_inbounds(user, [inbound])
    await storage.update_user_outbounds(
        user,
        [
            Outbound(
                protocol="socks",
                address="198.51.100.30",
                port=1080,
                inbound_tags=["res-in"],
            )
        ],
    )

    await storage.remove_user(user)

    assert await storage.list_users(9) is None
    assert await storage.list_user_outbounds(9) == []
    await _close(storage)
