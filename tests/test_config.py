"""Tests for marznode.config — env-driven module-level configuration."""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def reload_clean(monkeypatch):
    """Reload marznode.config with a sterile environment."""
    for name in (
        "SERVICE_ADDRESS",
        "SERVICE_PORT",
        "INSECURE",
        "XRAY_ENABLED",
        "XRAY_RESTART_ON_FAILURE",
        "XRAY_RESTART_ON_FAILURE_INTERVAL",
        "HYSTERIA_ENABLED",
        "SING_BOX_ENABLED",
        "SING_BOX_USER_MODIFICATION_INTERVAL",
        "MARZNODE_STORAGE_TYPE",
        "MARZNODE_DB_PATH",
        "DEBUG",
        "AUTH_GENERATION_ALGORITHM",
    ):
        monkeypatch.delenv(name, raising=False)

    def _reload():
        import marznode.config

        return importlib.reload(marznode.config)

    return _reload


def test_defaults_match_source(reload_clean):
    cfg = reload_clean()

    assert cfg.SERVICE_ADDRESS == "0.0.0.0"
    assert cfg.SERVICE_PORT == 53042
    assert cfg.INSECURE is False
    assert cfg.XRAY_ENABLED is True
    assert cfg.HYSTERIA_ENABLED is False
    assert cfg.SING_BOX_ENABLED is False
    assert cfg.SING_BOX_USER_MODIFICATION_INTERVAL == 30
    assert cfg.MARZNODE_STORAGE_TYPE == "memory"
    assert cfg.DEBUG is False
    assert cfg.AUTH_GENERATION_ALGORITHM == cfg.AuthAlgorithm.XXH128


def test_storage_type_lowercased(reload_clean, monkeypatch):
    monkeypatch.setenv("MARZNODE_STORAGE_TYPE", "SQLITE")
    cfg = reload_clean()
    assert cfg.MARZNODE_STORAGE_TYPE == "sqlite"


def test_int_cast(reload_clean, monkeypatch):
    monkeypatch.setenv("SERVICE_PORT", "9999")
    cfg = reload_clean()
    assert cfg.SERVICE_PORT == 9999


def test_bool_cast_true(reload_clean, monkeypatch):
    monkeypatch.setenv("INSECURE", "true")
    cfg = reload_clean()
    assert cfg.INSECURE is True


def test_bool_cast_false(reload_clean, monkeypatch):
    monkeypatch.setenv("XRAY_ENABLED", "false")
    cfg = reload_clean()
    assert cfg.XRAY_ENABLED is False


def test_auth_algorithm_plain(reload_clean, monkeypatch):
    monkeypatch.setenv("AUTH_GENERATION_ALGORITHM", "plain")
    cfg = reload_clean()
    assert cfg.AUTH_GENERATION_ALGORITHM == cfg.AuthAlgorithm.PLAIN


def test_auth_algorithm_invalid_raises(reload_clean, monkeypatch):
    monkeypatch.setenv("AUTH_GENERATION_ALGORITHM", "rot13")
    with pytest.raises(ValueError):
        reload_clean()
