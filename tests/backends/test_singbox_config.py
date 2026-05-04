"""Tests for marznode.backends.singbox._config.SingBoxConfig."""

from __future__ import annotations

import json

import pytest

from marznode.backends.singbox._config import SingBoxConfig
from marznode.models import Inbound, User


def test_resolves_supported_inbounds(singbox_minimal_config):
    cfg = SingBoxConfig(singbox_minimal_config)
    tags = set(cfg.inbounds_by_tag.keys())
    # `direct` is filtered out; the rest pass through.
    assert tags == {
        "sb-vmess",
        "sb-vless-reality",
        "sb-trojan-ws",
        "sb-hysteria",
        "sb-shadowtls",
    }


def test_apply_api_sets_v2ray_api(singbox_minimal_config):
    cfg = SingBoxConfig(singbox_minimal_config, api_host="127.0.0.1", api_port=9000)
    api = cfg["experimental"]["v2ray_api"]
    assert api["listen"] == "127.0.0.1:9000"
    assert api["stats"] == {"enabled": True, "users": []}


def test_apply_api_preserves_existing_experimental_keys():
    raw = json.dumps({
        "experimental": {"clash_api": {"external_controller": "127.0.0.1:9090"}},
        "inbounds": [],
    })
    cfg = SingBoxConfig(raw)
    assert cfg["experimental"]["clash_api"]["external_controller"] == "127.0.0.1:9090"
    assert "v2ray_api" in cfg["experimental"]


def test_reality_settings_picked_up(singbox_minimal_config):
    cfg = SingBoxConfig(singbox_minimal_config)
    s = cfg.inbounds_by_tag["sb-vless-reality"]
    assert s["tls"] == "reality"
    assert s["sni"] == ["example.com"]
    assert s["sid"] == "abcd1234"
    assert s["pbk"] == "PUBLIC-KEY-STUB"


def test_ws_transport_path(singbox_minimal_config):
    cfg = SingBoxConfig(singbox_minimal_config)
    s = cfg.inbounds_by_tag["sb-trojan-ws"]
    assert s["network"] == "ws"
    assert s["path"] == "/trojan"


def test_hysteria2_obfs_extracted(singbox_minimal_config):
    cfg = SingBoxConfig(singbox_minimal_config)
    s = cfg.inbounds_by_tag["sb-hysteria"]
    assert s["header_type"] == "salamander"
    assert s["path"] == "obfs-pass"


def test_shadowtls_version_extracted(singbox_minimal_config):
    cfg = SingBoxConfig(singbox_minimal_config)
    s = cfg.inbounds_by_tag["sb-shadowtls"]
    assert s["shadowtls_version"] == 3


def test_skips_inbound_without_tag():
    raw = json.dumps({"inbounds": [{"type": "vmess", "listen_port": 1}]})
    cfg = SingBoxConfig(raw)
    assert cfg.inbounds_by_tag == {}


def test_skips_unknown_protocol():
    raw = json.dumps({
        "inbounds": [{"type": "weird", "tag": "x", "listen_port": 1}]
    })
    cfg = SingBoxConfig(raw)
    assert cfg.inbounds_by_tag == {}


def test_append_user_adds_to_inbound_and_stats(singbox_minimal_config):
    cfg = SingBoxConfig(singbox_minimal_config)
    user = User(id=42, username="alice", key="seed", inbounds=[])
    inbound = Inbound(tag="sb-vmess", protocol="vmess", config={})

    cfg.append_user(user, inbound)

    raw_inbound = next(i for i in cfg["inbounds"] if i["tag"] == "sb-vmess")
    assert any(u.get("name") == "42.alice" for u in raw_inbound["users"])
    assert "42.alice" in cfg["experimental"]["v2ray_api"]["stats"]["users"]


def test_append_user_is_idempotent_in_stats(singbox_minimal_config):
    cfg = SingBoxConfig(singbox_minimal_config)
    user = User(id=42, username="alice", key="seed", inbounds=[])
    inbound = Inbound(tag="sb-vmess", protocol="vmess", config={})

    cfg.append_user(user, inbound)
    cfg.append_user(user, inbound)

    stats_users = cfg["experimental"]["v2ray_api"]["stats"]["users"]
    assert stats_users.count("42.alice") == 1


def test_pop_user_removes_from_inbound(singbox_minimal_config):
    cfg = SingBoxConfig(singbox_minimal_config)
    user = User(id=42, username="alice", key="seed", inbounds=[])
    inbound = Inbound(tag="sb-vmess", protocol="vmess", config={})

    cfg.append_user(user, inbound)
    cfg.pop_user(user, inbound)

    raw_inbound = next(i for i in cfg["inbounds"] if i["tag"] == "sb-vmess")
    assert all(u.get("name") != "42.alice" for u in raw_inbound["users"])


def test_pop_user_noop_when_tag_not_found(singbox_minimal_config):
    cfg = SingBoxConfig(singbox_minimal_config)
    user = User(id=42, username="alice", key="seed", inbounds=[])
    cfg.pop_user(user, Inbound(tag="missing", protocol="vmess", config={}))
    # Nothing crashed and existing inbounds still exist.
    assert "sb-vmess" in cfg.inbounds_by_tag


def test_register_inbounds_pushes_to_storage(singbox_minimal_config, memory_storage):
    cfg = SingBoxConfig(singbox_minimal_config)
    cfg.register_inbounds(memory_storage)
    assert "sb-vmess" in memory_storage.storage["inbounds"]


def test_to_json_roundtrips_dict(singbox_minimal_config):
    cfg = SingBoxConfig(singbox_minimal_config)
    parsed = json.loads(cfg.to_json())
    assert "experimental" in parsed
