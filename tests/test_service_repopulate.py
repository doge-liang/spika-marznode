import pytest

from marznode.models import Inbound, Outbound, User
from marznode.service.service import MarzService
from marznode.service.service_pb2 import (
    Empty,
    Inbound as PbInbound,
    Outbound as PbOutbound,
    User as PbUser,
    UserData,
    UsersData,
)
from marznode.storage.memory import MemoryStorage


class FakeBackend:
    backend_type = "xray"
    version = "test"

    def __init__(self, *tags: str):
        self.tags = set(tags)
        self.added = []
        self.removed = []

    def contains_tag(self, inbound_tag: str) -> bool:
        return inbound_tag in self.tags

    async def add_user(self, user: User, inbound: Inbound):
        self.added.append((user.id, user.username, user.key, inbound.tag))

    async def remove_user(self, user: User, inbound: Inbound):
        self.removed.append((user.id, user.username, user.key, inbound.tag))

    def list_inbounds(self):
        return []


class FakeStream:
    def __init__(self, request: UsersData):
        self.request = request
        self.sent = []

    async def recv_message(self):
        return self.request

    async def send_message(self, message):
        self.sent.append(message)


def _inbound(tag: str) -> Inbound:
    return Inbound(tag=tag, protocol="vless", config={"tag": tag})


def _user_data(
    uid: int,
    username: str,
    inbound_tags: list[str],
    outbounds: list[PbOutbound] | None = None,
) -> UserData:
    return UserData(
        user=PbUser(id=uid, username=username, key=f"k-{username}"),
        inbounds=[PbInbound(tag=tag) for tag in inbound_tags],
        outbounds=outbounds or [],
    )


@pytest.mark.asyncio
async def test_update_user_stores_submitted_outbounds():
    storage = MemoryStorage()
    inbound = _inbound("res-in")
    storage.register_inbound(inbound)
    backend = FakeBackend("res-in")
    service = MarzService(storage, {"xray": backend})

    await service._update_user(
        _user_data(
            7,
            "alice",
            ["res-in"],
            [
                PbOutbound(
                    protocol="socks",
                    address="198.51.100.10",
                    port=1080,
                    username="up-user",
                    password="up-pass",
                    inbound_tags=["res-in"],
                )
            ],
        )
    )

    stored = await storage.list_users(7)
    assert backend.added == [(7, "alice", "k-alice", "res-in")]
    assert [inbound.tag for inbound in stored.inbounds] == ["res-in"]
    assert [outbound.model_dump() for outbound in stored.outbounds] == [
        {
            "protocol": "socks",
            "address": "198.51.100.10",
            "port": 1080,
            "username": "up-user",
            "password": "up-pass",
            "inbound_tags": ["res-in"],
        }
    ]


@pytest.mark.asyncio
async def test_update_user_replaces_inbounds_and_clears_outbounds():
    storage = MemoryStorage()
    old_inbound = _inbound("old-in")
    new_inbound = _inbound("new-in")
    storage.register_inbound(old_inbound)
    storage.register_inbound(new_inbound)
    existing = User(id=8, username="carol", key="k-carol")
    await storage.update_user_inbounds(existing, [old_inbound])
    await storage.update_user_outbounds(
        existing,
        [
            Outbound(
                protocol="socks",
                address="198.51.100.11",
                port=1080,
                inbound_tags=["old-in"],
            )
        ],
    )
    backend = FakeBackend("old-in", "new-in")
    service = MarzService(storage, {"xray": backend})

    await service._update_user(_user_data(8, "carol", ["new-in"]))

    stored = await storage.list_users(8)
    assert backend.removed == [(8, "carol", "k-carol", "old-in")]
    assert backend.added == [(8, "carol", "k-carol", "new-in")]
    assert [inbound.tag for inbound in stored.inbounds] == ["new-in"]
    assert stored.outbounds == []


@pytest.mark.asyncio
async def test_update_existing_user_replaces_outbounds():
    storage = MemoryStorage()
    inbound = _inbound("res-in")
    storage.register_inbound(inbound)
    existing = User(id=10, username="dave", key="k-dave")
    await storage.update_user_inbounds(existing, [inbound])
    await storage.update_user_outbounds(
        existing,
        [
            Outbound(
                protocol="socks",
                address="198.51.100.50",
                port=1080,
                inbound_tags=["res-in"],
            )
        ],
    )
    service = MarzService(storage, {"xray": FakeBackend("res-in")})

    await service._update_user(
        _user_data(
            10,
            "dave",
            ["res-in"],
            [
                PbOutbound(
                    protocol="http",
                    address="203.0.113.50",
                    port=8080,
                    username="new-up",
                    password="new-pass",
                    inbound_tags=["res-in"],
                )
            ],
        )
    )

    stored = await storage.list_users(10)
    assert [outbound.model_dump() for outbound in stored.outbounds] == [
        {
            "protocol": "http",
            "address": "203.0.113.50",
            "port": 8080,
            "username": "new-up",
            "password": "new-pass",
            "inbound_tags": ["res-in"],
        }
    ]


@pytest.mark.asyncio
async def test_update_existing_user_replaces_changed_identity_on_same_inbounds():
    storage = MemoryStorage()
    inbound = _inbound("same-in")
    storage.register_inbound(inbound)
    existing = User(id=11, username="old-name", key="old-key")
    await storage.update_user_inbounds(existing, [inbound])
    backend = FakeBackend("same-in")
    service = MarzService(storage, {"xray": backend})

    await service._update_user(
        UserData(
            user=PbUser(id=11, username="new-name", key="new-key"),
            inbounds=[PbInbound(tag="same-in")],
        )
    )

    stored = await storage.list_users(11)
    assert backend.removed == [(11, "old-name", "old-key", "same-in")]
    assert backend.added == [(11, "new-name", "new-key", "same-in")]
    assert stored.username == "new-name"
    assert stored.key == "new-key"
    assert [inbound.tag for inbound in stored.inbounds] == ["same-in"]


@pytest.mark.asyncio
async def test_repopulate_users_removes_stale_local_users():
    storage = MemoryStorage()
    kept_inbound = _inbound("kept-in")
    stale_inbound = _inbound("stale-in")
    storage.register_inbound(kept_inbound)
    storage.register_inbound(stale_inbound)
    stale_user = User(id=99, username="stale", key="k-stale")
    await storage.update_user_inbounds(stale_user, [stale_inbound])
    backend = FakeBackend("kept-in", "stale-in")
    service = MarzService(storage, {"xray": backend})
    request = UsersData(
        users_data=[
            _user_data(
                7,
                "alice",
                ["kept-in"],
                [
                    PbOutbound(
                        protocol="http",
                        address="203.0.113.10",
                        port=8080,
                        inbound_tags=["kept-in"],
                    )
                ],
            )
        ]
    )
    stream = FakeStream(request)

    await service.RepopulateUsers(stream)

    assert isinstance(stream.sent[0], Empty)
    assert await storage.list_users(99) is None
    kept = await storage.list_users(7)
    assert [inbound.tag for inbound in kept.inbounds] == ["kept-in"]
    assert [outbound.address for outbound in kept.outbounds] == ["203.0.113.10"]
    assert backend.removed == [(99, "stale", "k-stale", "stale-in")]
