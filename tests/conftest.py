"""Shared fixtures for the marznode test suite."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Iterator

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Env vars that influence marznode.config. Each test starts with all of these
# cleared so behavior is deterministic regardless of the developer's shell.
_CONFIG_ENV_VARS = (
    "SERVICE_ADDRESS",
    "SERVICE_PORT",
    "INSECURE",
    "XRAY_ENABLED",
    "XRAY_EXECUTABLE_PATH",
    "XRAY_ASSETS_PATH",
    "XRAY_CONFIG_PATH",
    "XRAY_VLESS_REALITY_FLOW",
    "XRAY_RESTART_ON_FAILURE",
    "XRAY_RESTART_ON_FAILURE_INTERVAL",
    "HYSTERIA_ENABLED",
    "HYSTERIA_EXECUTABLE_PATH",
    "HYSTERIA_CONFIG_PATH",
    "SING_BOX_ENABLED",
    "SING_BOX_EXECUTABLE_PATH",
    "SING_BOX_CONFIG_PATH",
    "SING_BOX_RESTART_ON_FAILURE",
    "SING_BOX_RESTART_ON_FAILURE_INTERVAL",
    "SING_BOX_USER_MODIFICATION_INTERVAL",
    "SSL_CERT_FILE",
    "SSL_KEY_FILE",
    "SSL_CLIENT_CERT_FILE",
    "MARZNODE_STORAGE_TYPE",
    "MARZNODE_DB_PATH",
    "DEBUG",
    "AUTH_GENERATION_ALGORITHM",
)


def _purge_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _CONFIG_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def reload_config():
    """Reload marznode.config so module-level reads happen against current env."""
    import marznode.config as cfg

    return importlib.reload(cfg)


@pytest.fixture
def clean_config_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Strip config env vars and reload marznode.config; restore on teardown."""
    _purge_config_env(monkeypatch)
    reload_config()
    yield
    reload_config()


@pytest.fixture
def memory_storage():
    from marznode.storage.memory import MemoryStorage

    return MemoryStorage()


async def _close_sqlite(storage) -> None:
    """SqliteStorage doesn't expose close(); reach into _db so the worker
    thread shuts down cleanly before the event loop exits."""
    db = getattr(storage, "_db", None)
    if db is not None:
        try:
            await db.close()
        except Exception:
            pass
        storage._db = None


@pytest.fixture
async def sqlite_storage(tmp_path: Path):
    from marznode.storage.sqlite import SqliteStorage

    db = tmp_path / "marznode.db"
    storage = SqliteStorage(db_path=str(db))
    yield storage
    await _close_sqlite(storage)


@pytest.fixture(params=["memory", "sqlite"])
async def any_storage(request, tmp_path: Path):
    """Parametrized fixture that runs a test against both storage backends."""
    from marznode.storage.memory import MemoryStorage
    from marznode.storage.sqlite import SqliteStorage

    if request.param == "memory":
        yield MemoryStorage()
        return
    storage = SqliteStorage(db_path=str(tmp_path / "marznode.db"))
    yield storage
    await _close_sqlite(storage)


@pytest.fixture
def sample_inbound():
    from marznode.models import Inbound

    return Inbound(tag="vmess-tcp", protocol="vmess", config={"port": 12345})


@pytest.fixture
def other_inbound():
    from marznode.models import Inbound

    return Inbound(tag="vless-ws", protocol="vless", config={"port": 23456})


@pytest.fixture
def sample_user(sample_inbound):
    from marznode.models import User

    return User(id=1, username="alice", key="seed-alice", inbounds=[sample_inbound])


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


@pytest.fixture
def xray_minimal_config() -> str:
    return _load_fixture("xray_minimal.json")


@pytest.fixture
def xray_reality_config() -> str:
    return _load_fixture("xray_reality.json")


@pytest.fixture
def singbox_minimal_config() -> str:
    return _load_fixture("singbox_minimal.json")


@pytest.fixture(autouse=True)
def _stub_xray_x25519(monkeypatch):
    """Replace get_x25519 so tests never shell out to a real xray binary.

    Both the xray and sing-box config modules import `get_x25519` from
    `marznode.backends.xray._utils`. The real implementation runs the xray
    executable, which isn't available in CI.
    """
    fake = lambda *_a, **_kw: {
        "private_key": "PRIVATE-KEY-STUB",
        "public_key": "PUBLIC-KEY-STUB",
    }
    try:
        import marznode.backends.xray._utils as xu

        monkeypatch.setattr(xu, "get_x25519", fake)
    except Exception:
        pass
    try:
        import marznode.backends.xray._config as xc

        monkeypatch.setattr(xc, "get_x25519", fake, raising=False)
    except Exception:
        pass
    try:
        import marznode.backends.singbox._config as sc

        monkeypatch.setattr(sc, "get_x25519", fake, raising=False)
    except Exception:
        pass
