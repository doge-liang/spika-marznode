"""Tests for marznode.utils.key_gen."""

from __future__ import annotations

import importlib
import re
import uuid

import pytest


HEX32 = re.compile(r"^[0-9a-f]{32}$")


def _reload_with_algo(monkeypatch, algo: str):
    monkeypatch.setenv("AUTH_GENERATION_ALGORITHM", algo)
    import marznode.config

    importlib.reload(marznode.config)
    import marznode.utils.key_gen as kg

    importlib.reload(kg)
    return kg


def test_xxh128_uuid_is_deterministic(monkeypatch):
    kg = _reload_with_algo(monkeypatch, "xxh128")
    a = kg.generate_uuid("alice")
    b = kg.generate_uuid("alice")
    assert isinstance(a, uuid.UUID)
    assert a == b


def test_xxh128_uuid_differs_per_key(monkeypatch):
    kg = _reload_with_algo(monkeypatch, "xxh128")
    assert kg.generate_uuid("alice") != kg.generate_uuid("bob")


def test_xxh128_password_is_32_char_hex_and_deterministic(monkeypatch):
    kg = _reload_with_algo(monkeypatch, "xxh128")
    pw = kg.generate_password("alice")
    assert HEX32.match(pw), pw
    assert pw == kg.generate_password("alice")


def test_xxh128_password_differs_per_key(monkeypatch):
    kg = _reload_with_algo(monkeypatch, "xxh128")
    assert kg.generate_password("alice") != kg.generate_password("bob")


def test_plain_uuid_uses_input_as_uuid(monkeypatch):
    kg = _reload_with_algo(monkeypatch, "plain")
    raw = "12345678-1234-5678-1234-567812345678"
    assert kg.generate_uuid(raw) == uuid.UUID(raw)


def test_plain_uuid_rejects_non_uuid_input(monkeypatch):
    kg = _reload_with_algo(monkeypatch, "plain")
    with pytest.raises(ValueError):
        kg.generate_uuid("not-a-uuid")


def test_plain_password_returns_input(monkeypatch):
    kg = _reload_with_algo(monkeypatch, "plain")
    assert kg.generate_password("the-key") == "the-key"
