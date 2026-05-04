"""Behavior parity tests across MemoryStorage and SqliteStorage."""

from __future__ import annotations

import pytest

from marznode.models import Inbound, User


pytestmark = pytest.mark.asyncio


def _user(uid: int, username: str, key: str) -> User:
    return User(id=uid, username=username, key=key, inbounds=[])


def _inb(tag: str) -> Inbound:
    return Inbound(tag=tag, protocol="vmess", config={"port": 1000 + len(tag)})


async def test_register_and_list_inbounds(any_storage):
    a, b = _inb("a"), _inb("b")
    any_storage.register_inbound(a)
    any_storage.register_inbound(b)

    by_tag = await any_storage.list_inbounds(tag="a")
    assert by_tag is not None
    assert by_tag.tag == "a"

    subset = await any_storage.list_inbounds(tag=["a", "missing"])
    assert [i.tag for i in subset] == ["a"]

    all_inbounds = await any_storage.list_inbounds()
    assert {i.tag for i in all_inbounds} == {"a", "b"}


async def test_update_user_inbounds_creates_then_replaces(any_storage):
    a, b = _inb("a"), _inb("b")
    any_storage.register_inbound(a)
    any_storage.register_inbound(b)
    user = _user(1, "alice", "k")

    await any_storage.update_user_inbounds(user, [a, b])

    fetched = await any_storage.list_users(1)
    assert fetched is not None
    assert {i.tag for i in fetched.inbounds} == {"a", "b"}

    # Replace with a smaller set — leftovers must be cleared.
    await any_storage.update_user_inbounds(user, [a])

    fetched = await any_storage.list_users(1)
    assert {i.tag for i in fetched.inbounds} == {"a"}


async def test_list_inbound_users_filters_by_tag(any_storage):
    a, b = _inb("a"), _inb("b")
    any_storage.register_inbound(a)
    any_storage.register_inbound(b)
    alice = _user(1, "alice", "ka")
    bob = _user(2, "bob", "kb")
    await any_storage.update_user_inbounds(alice, [a])
    await any_storage.update_user_inbounds(bob, [a, b])

    on_a = await any_storage.list_inbound_users("a")
    on_b = await any_storage.list_inbound_users("b")

    assert {u.id for u in on_a} == {1, 2}
    assert {u.id for u in on_b} == {2}


async def test_remove_user(any_storage):
    a = _inb("a")
    any_storage.register_inbound(a)
    user = _user(1, "alice", "k")
    await any_storage.update_user_inbounds(user, [a])

    await any_storage.remove_user(user)

    assert await any_storage.list_users(1) is None
    assert await any_storage.list_inbound_users("a") == []


async def test_flush_users_keeps_inbounds(any_storage):
    a = _inb("a")
    any_storage.register_inbound(a)
    await any_storage.update_user_inbounds(_user(1, "alice", "k"), [a])
    await any_storage.update_user_inbounds(_user(2, "bob", "k"), [a])

    await any_storage.flush_users()

    assert await any_storage.list_users() == []
    inbounds = await any_storage.list_inbounds()
    assert [i.tag for i in inbounds] == ["a"]


async def test_list_users_returns_empty_list_when_no_users(any_storage):
    result = await any_storage.list_users()
    assert result == []


async def test_list_users_by_unknown_id_returns_none(any_storage):
    assert await any_storage.list_users(99) is None
