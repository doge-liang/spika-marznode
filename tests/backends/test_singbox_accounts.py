"""Tests for marznode.backends.singbox._accounts.accounts_map."""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def accounts_map(monkeypatch):
    monkeypatch.setenv("AUTH_GENERATION_ALGORITHM", "xxh128")
    import marznode.config

    importlib.reload(marznode.config)
    import marznode.utils.key_gen as kg

    importlib.reload(kg)
    import marznode.backends.singbox._accounts as accounts

    importlib.reload(accounts)
    return accounts.accounts_map


@pytest.mark.parametrize(
    "protocol",
    [
        "shadowsocks",
        "trojan",
        "vmess",
        "vless",
        "shadowtls",
        "tuic",
        "hysteria2",
        "naive",
        "socks",
        "mixed",
        "http",
    ],
)
def test_each_protocol_account_is_deterministic(accounts_map, protocol):
    AccountCls = accounts_map[protocol]
    a = AccountCls(identifier="42.alice", seed="seed-alice")
    b = AccountCls(identifier="42.alice", seed="seed-alice")
    assert a.to_dict() == b.to_dict()


@pytest.mark.parametrize(
    "protocol", ["shadowsocks", "trojan", "vmess", "vless", "tuic", "hysteria2"]
)
def test_each_protocol_account_differs_per_seed(accounts_map, protocol):
    AccountCls = accounts_map[protocol]
    a = AccountCls(identifier="42.alice", seed="seed-alice")
    b = AccountCls(identifier="42.alice", seed="seed-bob")
    assert a.to_dict() != b.to_dict()


def test_to_dict_strips_seed_and_identifier(accounts_map):
    cls = accounts_map["vmess"]
    acc = cls(identifier="42.alice", seed="seed")
    d = acc.to_dict()
    assert "seed" not in d
    assert "identifier" not in d
    # NamedAccount adds `name` (computed from identifier)
    assert d["name"] == "42.alice"


def test_user_named_account_uses_username_field(accounts_map):
    cls = accounts_map["socks"]
    acc = cls(identifier="42.alice", seed="seed")
    d = acc.to_dict()
    assert d["username"] == "42.alice"
    assert "name" not in d


def test_protocols_covered():
    """Guard that every protocol mentioned in singbox._config._resolve_inbounds
    has an entry in accounts_map (so append_user won't KeyError)."""
    import marznode.backends.singbox._accounts as accounts

    expected = {
        "shadowsocks",
        "trojan",
        "vmess",
        "vless",
        "shadowtls",
        "tuic",
        "hysteria2",
    }
    assert expected.issubset(set(accounts.accounts_map.keys()))
