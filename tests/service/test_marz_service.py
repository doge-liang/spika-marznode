"""Tests for marznode.service.service.MarzService."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from grpclib import GRPCError, Status

from marznode.backends.abstract_backend import VPNBackend
from marznode.models import Inbound, User
from marznode.service.service import MarzService
from marznode.service.service_pb2 import (
    Backend,
    BackendLogsRequest,
    Empty,
    Inbound as InboundPb,
    User as UserPb,
    UserData,
    UsersData,
)


pytestmark = pytest.mark.asyncio


class FakeBackend(VPNBackend):
    backend_type = "fake"
    config_format = 0

    def __init__(self, tags: list[str], usages: dict[int, int] | None = None):
        self._tags = set(tags)
        self._usages = usages or {}
        self.added: list[tuple[User, Inbound]] = []
        self.removed: list[tuple[User, Inbound]] = []
        self.restarted_with: Any = None

    @property
    def version(self):
        return "0.0.0"

    @property
    def running(self) -> bool:
        return True

    def contains_tag(self, tag: str) -> bool:
        return tag in self._tags

    async def start(self, backend_config: Any) -> None:
        return None

    async def restart(self, backend_config: Any) -> None:
        self.restarted_with = backend_config

    async def add_user(self, user: User, inbound: Inbound) -> None:
        self.added.append((user, inbound))

    async def remove_user(self, user: User, inbound: Inbound) -> None:
        self.removed.append((user, inbound))

    async def get_logs(self, include_buffer: bool) -> AsyncIterator[str]:
        for line in ("line-1", "line-2"):
            yield line

    async def get_usages(self):
        return dict(self._usages)

    def list_inbounds(self):
        return [
            Inbound(tag=t, protocol="vmess", config={"port": 1000})
            for t in sorted(self._tags)
        ]

    def get_config(self):
        return "fake-config"


class FakeStream:
    """A stand-in for grpclib.server.Stream that records sent messages."""

    def __init__(self, incoming=()):
        self._incoming = list(incoming)
        self.sent: list = []

    async def recv_message(self):
        if not self._incoming:
            return None
        return self._incoming.pop(0)

    async def send_message(self, msg):
        self.sent.append(msg)

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        while self._incoming:
            yield self._incoming.pop(0)


def _user_pb(uid: int, username: str, key: str) -> UserPb:
    return UserPb(id=uid, username=username, key=key)


def _user_data(uid: int, username: str, key: str, tags: list[str]) -> UserData:
    return UserData(
        user=_user_pb(uid, username, key),
        inbounds=[InboundPb(tag=t) for t in tags],
    )


@pytest.fixture
async def storage_with_inbounds(memory_storage):
    """Memory storage seeded with two inbounds."""
    memory_storage.register_inbound(
        Inbound(tag="vmess-tcp", protocol="vmess", config={"port": 1})
    )
    memory_storage.register_inbound(
        Inbound(tag="vless-ws", protocol="vless", config={"port": 2})
    )
    return memory_storage


@pytest.fixture
def fake_backend():
    return FakeBackend(tags=["vmess-tcp", "vless-ws"])


@pytest.fixture
def service(storage_with_inbounds, fake_backend):
    return MarzService(storage_with_inbounds, {"fake": fake_backend})


# ---- _update_user paths ----------------------------------------------------


async def test_update_user_add_path(service, fake_backend, storage_with_inbounds):
    await service._update_user(_user_data(1, "alice", "k", ["vmess-tcp"]))

    assert [t.tag for _, t in fake_backend.added] == ["vmess-tcp"]
    fetched = await storage_with_inbounds.list_users(1)
    assert fetched is not None
    assert {i.tag for i in fetched.inbounds} == {"vmess-tcp"}


async def test_update_user_delete_path(service, fake_backend, storage_with_inbounds):
    # Seed
    await service._update_user(_user_data(1, "alice", "k", ["vmess-tcp"]))
    fake_backend.added.clear()

    await service._update_user(_user_data(1, "alice", "k", []))

    assert [t.tag for _, t in fake_backend.removed] == ["vmess-tcp"]
    assert await storage_with_inbounds.list_users(1) is None


async def test_update_user_noop_when_unknown_and_empty(
    service, fake_backend, storage_with_inbounds
):
    await service._update_user(_user_data(99, "ghost", "k", []))

    assert fake_backend.added == []
    assert fake_backend.removed == []
    assert await storage_with_inbounds.list_users(99) is None


async def test_update_user_diff_only_adds_and_removes_changed_tags(
    service, fake_backend, storage_with_inbounds
):
    await service._update_user(_user_data(1, "alice", "k", ["vmess-tcp"]))
    fake_backend.added.clear()
    fake_backend.removed.clear()

    # Switch from vmess-tcp to vless-ws.
    await service._update_user(_user_data(1, "alice", "k", ["vless-ws"]))

    assert [t.tag for _, t in fake_backend.added] == ["vless-ws"]
    assert [t.tag for _, t in fake_backend.removed] == ["vmess-tcp"]
    fetched = await storage_with_inbounds.list_users(1)
    assert {i.tag for i in fetched.inbounds} == {"vless-ws"}


# ---- streaming RPCs --------------------------------------------------------


async def test_sync_users_consumes_stream(service, fake_backend):
    stream = FakeStream(
        [
            _user_data(1, "alice", "ka", ["vmess-tcp"]),
            _user_data(2, "bob", "kb", ["vless-ws"]),
        ]
    )

    await service.SyncUsers(stream)

    assert {u.username for u, _ in fake_backend.added} == {"alice", "bob"}


async def test_repopulate_users_removes_users_not_in_batch(
    service, fake_backend, storage_with_inbounds
):
    await service._update_user(_user_data(1, "alice", "k", ["vmess-tcp"]))
    await service._update_user(_user_data(2, "bob", "k", ["vless-ws"]))
    fake_backend.added.clear()
    fake_backend.removed.clear()

    stream = FakeStream(
        [UsersData(users_data=[_user_data(1, "alice", "k", ["vmess-tcp"])])]
    )

    await service.RepopulateUsers(stream)

    remaining = await storage_with_inbounds.list_users()
    assert {u.id for u in remaining} == {1}
    # bob's removal must hit the backend.
    assert any(u.username == "bob" for u, _ in fake_backend.removed)


# ---- non-streaming RPCs ----------------------------------------------------


async def test_fetch_backends_returns_each_backend_with_inbounds(service):
    stream = FakeStream([Empty()])
    await service.FetchBackends(stream)

    [resp] = stream.sent
    assert len(resp.backends) == 1
    backend = resp.backends[0]
    assert backend.name == "fake"
    assert backend.type == "fake"
    assert {i.tag for i in backend.inbounds} == {"vmess-tcp", "vless-ws"}
    # configs are JSON-encoded.
    for i in backend.inbounds:
        assert json.loads(i.config)["port"] >= 1000


async def test_fetch_users_stats_sums_across_backends(storage_with_inbounds):
    a = FakeBackend(tags=["vmess-tcp"], usages={1: 100, 2: 50})
    b = FakeBackend(tags=["vless-ws"], usages={1: 25, 3: 200})
    service = MarzService(storage_with_inbounds, {"a": a, "b": b})

    stream = FakeStream([Empty()])
    await service.FetchUsersStats(stream)

    [resp] = stream.sent
    by_uid = {s.uid: s.usage for s in resp.users_stats}
    assert by_uid == {1: 125, 2: 50, 3: 200}


async def test_get_backend_stats_unknown_raises_not_found(service):
    stream = FakeStream([Backend(name="nope")])
    with pytest.raises(GRPCError) as exc:
        await service.GetBackendStats(stream)
    assert exc.value.status == Status.NOT_FOUND


async def test_get_backend_stats_returns_running_flag(service):
    stream = FakeStream([Backend(name="fake")])
    await service.GetBackendStats(stream)
    [resp] = stream.sent
    assert resp.running is True


async def test_fetch_backend_config_returns_config_string(service):
    stream = FakeStream([Backend(name="fake")])
    await service.FetchBackendConfig(stream)
    [resp] = stream.sent
    assert resp.configuration == "fake-config"


async def test_restart_backend_passes_config_through(service, fake_backend):
    from marznode.service.service_pb2 import (
        BackendConfig as BackendConfigPb,
        RestartBackendRequest,
    )

    stream = FakeStream(
        [
            RestartBackendRequest(
                backend_name="fake",
                config=BackendConfigPb(configuration="new-config"),
            )
        ]
    )
    await service.RestartBackend(stream)
    assert fake_backend.restarted_with == "new-config"


async def test_stream_backend_logs_yields_buffered_lines(service):
    stream = FakeStream(
        [BackendLogsRequest(backend_name="fake", include_buffer=True)]
    )
    await service.StreamBackendLogs(stream)
    assert [m.line for m in stream.sent] == ["line-1", "line-2"]


# ---- known fragile paths ---------------------------------------------------


async def test_resolve_tag_unknown_raises(service):
    """_resolve_tag uses a bare `raise` (service.py:48) when no backend owns
    the tag. We test the current behavior and document it as a known issue —
    a bare `raise` outside an except-block raises RuntimeError. A follow-up
    should use a typed exception."""
    with pytest.raises(RuntimeError):
        service._resolve_tag("does-not-exist")
