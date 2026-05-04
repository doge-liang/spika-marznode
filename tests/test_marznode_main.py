"""Tests for marznode.marznode — the process entry point and storage selector."""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def fresh_marznode(monkeypatch):
    """Reload marznode.marznode against a clean env so config defaults apply."""
    for name in (
        "MARZNODE_STORAGE_TYPE",
        "MARZNODE_DB_PATH",
        "INSECURE",
        "SSL_CERT_FILE",
        "SSL_KEY_FILE",
        "SSL_CLIENT_CERT_FILE",
        "XRAY_ENABLED",
        "HYSTERIA_ENABLED",
        "SING_BOX_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    import marznode.config

    importlib.reload(marznode.config)
    import marznode.marznode as mn

    return importlib.reload(mn)


def test_build_storage_returns_memory_by_default(fresh_marznode):
    storage = fresh_marznode._build_storage()
    from marznode.storage.memory import MemoryStorage

    assert isinstance(storage, MemoryStorage)


def test_build_storage_returns_sqlite_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("MARZNODE_STORAGE_TYPE", "sqlite")
    monkeypatch.setenv("MARZNODE_DB_PATH", str(tmp_path / "marznode.db"))

    import marznode.config

    importlib.reload(marznode.config)
    import marznode.marznode as mn

    importlib.reload(mn)

    storage = mn._build_storage()
    from marznode.storage.sqlite import SqliteStorage

    assert isinstance(storage, SqliteStorage)


def test_build_storage_falls_back_to_memory_for_unknown_type(monkeypatch, caplog):
    monkeypatch.setenv("MARZNODE_STORAGE_TYPE", "redis")  # not supported

    import marznode.config

    importlib.reload(marznode.config)
    import marznode.marznode as mn

    importlib.reload(mn)

    with caplog.at_level("WARNING"):
        storage = mn._build_storage()

    from marznode.storage.memory import MemoryStorage

    assert isinstance(storage, MemoryStorage)
    assert any("Unknown MARZNODE_STORAGE_TYPE" in r.message for r in caplog.records)


# ---- main() startup wiring -------------------------------------------------


@pytest.mark.asyncio
async def test_main_insecure_no_backends_starts_and_stops(monkeypatch):
    """With INSECURE=true and all backends disabled, main() should wire up
    the gRPC server and exit cleanly when wait_closed returns."""
    monkeypatch.setenv("INSECURE", "true")
    monkeypatch.setenv("XRAY_ENABLED", "false")
    monkeypatch.setenv("HYSTERIA_ENABLED", "false")
    monkeypatch.setenv("SING_BOX_ENABLED", "false")

    import marznode.config

    importlib.reload(marznode.config)
    import marznode.marznode as mn

    importlib.reload(mn)

    fake_server = MagicMock()
    fake_server.start = AsyncMock()
    fake_server.wait_closed = AsyncMock()
    monkeypatch.setattr(mn, "Server", lambda *a, **kw: fake_server)
    # graceful_exit is a context manager that registers signal handlers; bypass.
    monkeypatch.setattr(
        mn, "graceful_exit", lambda *_a, **_kw: _NullCtx()
    )

    await mn.main()

    fake_server.start.assert_awaited_once()
    fake_server.wait_closed.assert_awaited_once()
    # ssl=None passed because INSECURE.
    _, kwargs = fake_server.start.call_args
    assert kwargs.get("ssl") is None


@pytest.mark.asyncio
async def test_main_exits_when_client_cert_missing(monkeypatch, tmp_path):
    """When TLS is required but SSL_CLIENT_CERT_FILE doesn't exist,
    main() must call sys.exit(1) (marznode.py:58-60)."""
    monkeypatch.setenv("INSECURE", "false")
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "server.crt"))
    monkeypatch.setenv("SSL_KEY_FILE", str(tmp_path / "server.key"))
    monkeypatch.setenv("SSL_CLIENT_CERT_FILE", str(tmp_path / "missing.crt"))
    monkeypatch.setenv("XRAY_ENABLED", "false")
    monkeypatch.setenv("HYSTERIA_ENABLED", "false")
    monkeypatch.setenv("SING_BOX_ENABLED", "false")

    import marznode.config

    importlib.reload(marznode.config)
    import marznode.marznode as mn

    importlib.reload(mn)

    # generate_keypair would write real files; replace with a no-op.
    monkeypatch.setattr(mn, "generate_keypair", lambda *a, **kw: None)
    monkeypatch.setattr(mn, "create_secure_context", lambda *a, **kw: object())

    with pytest.raises(SystemExit) as exc:
        await mn.main()
    assert exc.value.code == 1


@pytest.mark.asyncio
async def test_main_generates_keypair_when_server_files_missing(monkeypatch, tmp_path):
    """Missing server cert+key triggers generate_keypair (marznode.py:52-56)."""
    cert = tmp_path / "server.crt"
    key = tmp_path / "server.key"
    client_cert = tmp_path / "client.crt"
    client_cert.write_text("dummy")  # exists, so we don't hit sys.exit

    monkeypatch.setenv("INSECURE", "false")
    monkeypatch.setenv("SSL_CERT_FILE", str(cert))
    monkeypatch.setenv("SSL_KEY_FILE", str(key))
    monkeypatch.setenv("SSL_CLIENT_CERT_FILE", str(client_cert))
    monkeypatch.setenv("XRAY_ENABLED", "false")
    monkeypatch.setenv("HYSTERIA_ENABLED", "false")
    monkeypatch.setenv("SING_BOX_ENABLED", "false")

    import marznode.config

    importlib.reload(marznode.config)
    import marznode.marznode as mn

    importlib.reload(mn)

    keypair_calls = []

    def _fake_keypair(key_path, cert_path):
        keypair_calls.append((key_path, cert_path))

    monkeypatch.setattr(mn, "generate_keypair", _fake_keypair)
    monkeypatch.setattr(mn, "create_secure_context", lambda *a, **kw: object())

    fake_server = MagicMock()
    fake_server.start = AsyncMock()
    fake_server.wait_closed = AsyncMock()
    monkeypatch.setattr(mn, "Server", lambda *a, **kw: fake_server)
    monkeypatch.setattr(mn, "graceful_exit", lambda *_a, **_kw: _NullCtx())

    await mn.main()

    assert keypair_calls == [(str(key), str(cert))]


class _NullCtx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
