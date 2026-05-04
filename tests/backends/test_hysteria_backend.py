"""Tests for marznode.backends.hysteria2.hysteria2_backend.HysteriaBackend."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aioresponses import aioresponses

from marznode.backends.hysteria2.hysteria2_backend import HysteriaBackend
from marznode.models import Inbound, User


def _build_backend(memory_storage):
    backend = HysteriaBackend.__new__(HysteriaBackend)
    backend._app_runner = None
    backend._executable_path = "/nonexistent/hysteria"
    backend._storage = memory_storage
    backend._inbound_tags = ["hysteria2"]
    backend._inbounds = []
    backend._users = {}
    backend._auth_site = None
    backend._runner = MagicMock()
    backend._stats_secret = "secret-token"
    backend._stats_port = 12345
    backend._config_path = "/nonexistent/hysteria.yaml"
    import asyncio

    backend._restart_lock = asyncio.Lock()
    return backend


def test_contains_tag_only_matches_hysteria2(memory_storage):
    b = _build_backend(memory_storage)
    assert b.contains_tag("hysteria2") is True
    assert b.contains_tag("xray-vmess") is False


async def test_add_user_registers_password_in_users_map(memory_storage):
    b = _build_backend(memory_storage)
    user = User(id=1, username="alice", key="seed-a", inbounds=[])
    inbound = Inbound(tag="hysteria2", protocol="hysteria2", config={})

    await b.add_user(user, inbound)

    assert len(b._users) == 1
    [stored] = list(b._users.values())
    assert stored is user


async def test_remove_user_removes_from_users_and_calls_kick(memory_storage):
    b = _build_backend(memory_storage)
    user = User(id=1, username="alice", key="seed-a", inbounds=[])
    inbound = Inbound(tag="hysteria2", protocol="hysteria2", config={})
    await b.add_user(user, inbound)

    with aioresponses() as mock:
        mock.post(f"http://127.0.0.1:{b._stats_port}/kick", status=200)
        await b.remove_user(user, inbound)

    assert b._users == {}


async def test_remove_user_short_circuits_when_not_present(memory_storage):
    b = _build_backend(memory_storage)
    user = User(id=1, username="alice", key="seed-a", inbounds=[])
    inbound = Inbound(tag="hysteria2", protocol="hysteria2", config={})

    # No HTTP call expected. aioresponses with no mocks raises if any HTTP fires.
    with aioresponses():
        await b.remove_user(user, inbound)


def _read_body(response: web.Response) -> bytes:
    """aiohttp.web.Response wraps the body in a Payload. Pull the raw bytes."""
    body = response.body
    if hasattr(body, "_value"):
        body = body._value
    if isinstance(body, str):
        body = body.encode()
    return body


async def test_auth_callback_accepts_known_user(memory_storage):
    b = _build_backend(memory_storage)
    user = User(id=42, username="alice", key="seed-a", inbounds=[])
    inbound = Inbound(tag="hysteria2", protocol="hysteria2", config={})
    await b.add_user(user, inbound)
    [password] = list(b._users.keys())

    request = MagicMock(spec=web.Request)
    request.json = AsyncMock(return_value={"auth": password})

    response = await b._auth_callback(request)
    assert response.status == 200
    body = json.loads(_read_body(response))
    assert body == {"ok": True, "id": "42.alice"}


async def test_auth_callback_rejects_unknown_user(memory_storage):
    b = _build_backend(memory_storage)
    request = MagicMock(spec=web.Request)
    request.json = AsyncMock(return_value={"auth": "definitely-not-a-key"})

    response = await b._auth_callback(request)
    assert response.status == 404


async def test_get_usages_parses_traffic_payload(memory_storage):
    b = _build_backend(memory_storage)
    payload = {
        "1.alice": {"tx": 100, "rx": 50},
        "2.bob": {"tx": 0, "rx": 1024},
    }
    with aioresponses() as mock:
        url = f"http://127.0.0.1:{b._stats_port}/traffic?clear=1"
        mock.get(url, status=200, payload=payload)
        usages = await b.get_usages()

    assert usages == {1: 150, 2: 1024}


async def test_get_usages_returns_empty_on_connection_error(memory_storage):
    from aiohttp import ClientConnectorError

    b = _build_backend(memory_storage)
    with aioresponses() as mock:
        url = f"http://127.0.0.1:{b._stats_port}/traffic?clear=1"
        mock.get(
            url,
            exception=ClientConnectorError(MagicMock(), OSError("refused")),
        )
        usages = await b.get_usages()

    assert usages == {}


def test_save_and_get_config(tmp_path, memory_storage):
    cfg_path = tmp_path / "hysteria.yaml"
    cfg_path.write_text("listen: :443\n")
    b = _build_backend(memory_storage)
    b._config_path = str(cfg_path)

    assert b.get_config() == "listen: :443\n"

    b.save_config("listen: :8443\n")
    assert cfg_path.read_text() == "listen: :8443\n"
