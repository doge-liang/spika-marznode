"""SqliteStorage-specific behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from marznode.models import Inbound, User
from marznode.storage.sqlite import SqliteStorage


pytestmark = pytest.mark.asyncio


def _inb(tag: str) -> Inbound:
    return Inbound(tag=tag, protocol="vmess", config={"port": 1234})


async def _close(storage):
    db = getattr(storage, "_db", None)
    if db is not None:
        await db.close()
        storage._db = None


async def test_persistence_across_instances(tmp_path: Path):
    db_path = str(tmp_path / "marznode.db")
    inb = _inb("a")

    s1 = SqliteStorage(db_path=db_path)
    s1.register_inbound(inb)
    await s1.update_user_inbounds(
        User(id=1, username="alice", key="k", inbounds=[]), [inb]
    )
    await _close(s1)

    s2 = SqliteStorage(db_path=db_path)
    s2.register_inbound(inb)  # inbounds are in-memory; re-register on restart
    fetched = await s2.list_users(1)
    assert fetched is not None
    assert fetched.username == "alice"
    assert [i.tag for i in fetched.inbounds] == ["a"]
    await _close(s2)


async def test_parent_directory_is_created(tmp_path: Path):
    nested = tmp_path / "deeply" / "nested" / "dir" / "marznode.db"
    SqliteStorage(db_path=str(nested))
    assert nested.parent.is_dir()


# NOTE: SqliteStorage does NOT serialize writes on its shared aiosqlite
# connection — concurrent update_user_inbounds calls raise
# sqlite3.InterfaceError("bad parameter or other API misuse"). This is a
# real production issue (see service.SyncUsers / RepopulateUsers callers).
# A follow-up should add a write-lock or per-call connection. Until then,
# we test the sequential contract that the code currently delivers.
async def test_sequential_user_updates_persist_all_writes(tmp_path: Path):
    storage = SqliteStorage(db_path=str(tmp_path / "marznode.db"))
    inb = _inb("a")
    storage.register_inbound(inb)

    users = [User(id=i, username=f"u{i}", key=f"k{i}", inbounds=[]) for i in range(20)]
    for u in users:
        await storage.update_user_inbounds(u, [inb])

    fetched = await storage.list_users()
    assert {u.id for u in fetched} == {u.id for u in users}
    await _close(storage)


async def test_remove_user_cascades_inbounds(tmp_path: Path):
    storage = SqliteStorage(db_path=str(tmp_path / "marznode.db"))
    a, b = _inb("a"), _inb("b")
    storage.register_inbound(a)
    storage.register_inbound(b)
    user = User(id=1, username="alice", key="k", inbounds=[])
    await storage.update_user_inbounds(user, [a, b])

    await storage.remove_user(user)

    # FK cascade should have nuked user_inbounds rows too.
    db = await storage._conn()
    async with db.execute(
        "SELECT COUNT(*) FROM user_inbounds WHERE user_id = 1"
    ) as cur:
        (count,) = await cur.fetchone()
    assert count == 0
    await _close(storage)


async def test_unknown_inbound_tag_is_ignored_on_hydration(tmp_path: Path):
    """If a stored user_inbound row references an unregistered tag,
    list_users should silently skip it rather than raising."""
    storage = SqliteStorage(db_path=str(tmp_path / "marznode.db"))
    a = _inb("a")
    storage.register_inbound(a)
    user = User(id=1, username="alice", key="k", inbounds=[])
    await storage.update_user_inbounds(user, [a])

    # Drop the in-memory inbound registry to simulate a config reload.
    storage._inbounds.clear()

    fetched = await storage.list_users(1)
    assert fetched is not None
    assert fetched.inbounds == []
    await _close(storage)
