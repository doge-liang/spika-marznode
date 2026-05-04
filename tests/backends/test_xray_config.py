"""Tests for marznode.backends.xray._config.XrayConfig."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marznode.backends.xray._config import XrayConfig, merge_dicts, transport_map


def test_merge_dicts_recursive():
    a = {"x": {"y": 1, "z": 2}, "k": 5}
    b = {"x": {"z": 9, "new": 8}, "extra": True}
    result = merge_dicts(a, b)
    assert result == {"x": {"y": 1, "z": 9, "new": 8}, "k": 5, "extra": True}


def test_transport_map_known_aliases():
    assert transport_map["raw"] == "tcp"
    assert transport_map["xhttp"] == "splithttp"
    assert transport_map["websocket"] == "ws"
    assert transport_map["mkcp"] == "kcp"


def test_transport_map_unknown_falls_back_to_tcp():
    assert transport_map["something-weird"] == "tcp"


def test_constructor_accepts_json_string(xray_minimal_config):
    cfg = XrayConfig(xray_minimal_config)
    tags = {i["tag"] for i in cfg.inbounds}
    # `no-tag-skipped-because-protocol` has protocol=dokodemo-door — skipped.
    assert tags == {"vmess-tcp", "vless-ws", "trojan-grpc", "shadowsocks-1"}


def test_constructor_accepts_file_path(tmp_path: Path, xray_minimal_config):
    path = tmp_path / "xray.json"
    path.write_text(xray_minimal_config)
    cfg = XrayConfig(str(path))
    assert "vmess-tcp" in cfg.inbounds_by_tag


def test_apply_api_inserts_api_inbound_at_index_zero(xray_minimal_config):
    cfg = XrayConfig(xray_minimal_config, api_host="127.0.0.1", api_port=12345)
    assert cfg["inbounds"][0]["tag"] == "API_INBOUND"
    assert cfg["inbounds"][0]["port"] == 12345
    assert cfg["inbounds"][0]["protocol"] == "dokodemo-door"


def test_apply_api_inserts_api_routing_rule_first(xray_minimal_config):
    cfg = XrayConfig(xray_minimal_config)
    rule = cfg["routing"]["rules"][0]
    assert rule["inboundTag"] == ["API_INBOUND"]
    assert rule["outboundTag"] == "API"


def test_apply_api_merges_existing_policy(xray_reality_config):
    """forced_policies overrides user-supplied keys (merge order: user, then forced).
    Keys present only in the user policy must survive."""
    config = (
        '{"policy": {"system": {"statsInboundDownlink": true, "userOnlyKey": 7}, '
        '"userTopLevel": {"a": 1}}, "inbounds": []}'
    )
    cfg = XrayConfig(config)
    # forced wins over user where keys collide
    assert cfg["policy"]["system"]["statsInboundDownlink"] is False
    # forced-only key gets added
    assert cfg["policy"]["system"]["statsOutboundDownlink"] is True
    # user-only sibling survives
    assert cfg["policy"]["system"]["userOnlyKey"] == 7
    assert cfg["policy"]["userTopLevel"] == {"a": 1}
    assert cfg["policy"]["levels"]["0"]["statsUserUplink"] is True


def test_apply_api_uses_forced_policy_when_none_supplied(xray_minimal_config):
    cfg = XrayConfig(xray_minimal_config)
    assert cfg["policy"]["levels"]["0"]["statsUserUplink"] is True
    assert cfg["policy"]["system"]["statsOutboundDownlink"] is True


def test_resolve_tcp_header_path_and_host(xray_minimal_config):
    cfg = XrayConfig(xray_minimal_config)
    s = cfg.inbounds_by_tag["vmess-tcp"]
    assert s["network"] == "tcp"
    assert s["header_type"] == "http"
    assert s["path"] == "/api"
    assert s["host"] == ["example.com", "alt.example.com"]


def test_resolve_ws_path_and_tls(xray_minimal_config):
    cfg = XrayConfig(xray_minimal_config)
    s = cfg.inbounds_by_tag["vless-ws"]
    assert s["network"] == "ws"
    assert s["path"] == "/ws"
    assert s["host"] == "ws.example.com"
    assert s["tls"] == "tls"


def test_resolve_grpc_service_name(xray_minimal_config):
    cfg = XrayConfig(xray_minimal_config)
    s = cfg.inbounds_by_tag["trojan-grpc"]
    assert s["network"] == "grpc"
    assert s["path"] == "trojan-service"


def test_resolve_shadowsocks_clears_network(xray_minimal_config):
    cfg = XrayConfig(xray_minimal_config)
    s = cfg.inbounds_by_tag["shadowsocks-1"]
    assert s["network"] is None
    assert s["protocol"] == "shadowsocks"


def test_resolve_vless_reality_sets_flow_and_publickey(xray_reality_config):
    cfg = XrayConfig(xray_reality_config)
    s = cfg.inbounds_by_tag["vless-reality-tcp"]
    assert s["tls"] == "reality"
    assert s["fp"] == "chrome"
    # vless + tcp → flow set from XRAY_VLESS_REALITY_FLOW
    assert s["flow"] == "xtls-rprx-vision"
    assert s["sni"] == ["www.example.com", "alt.example.com"]
    assert s["sid"] == "abcd1234"
    # _stub_xray_x25519 fixture replaces get_x25519
    assert s["pbk"] == "PUBLIC-KEY-STUB"


def test_list_inbounds_returns_pydantic_models(xray_minimal_config):
    cfg = XrayConfig(xray_minimal_config)
    inbounds = cfg.list_inbounds()
    assert {i.tag for i in inbounds} == {
        "vmess-tcp",
        "vless-ws",
        "trojan-grpc",
        "shadowsocks-1",
    }
    for inb in inbounds:
        assert inb.protocol in {"vmess", "vless", "trojan", "shadowsocks"}
        assert isinstance(inb.config, dict)


def test_register_inbounds_pushes_to_storage(xray_minimal_config, memory_storage):
    cfg = XrayConfig(xray_minimal_config)
    cfg.register_inbounds(memory_storage)
    stored = memory_storage.storage["inbounds"]
    assert {"vmess-tcp", "vless-ws", "trojan-grpc", "shadowsocks-1"}.issubset(
        stored.keys()
    )


def test_to_json_roundtrip(xray_minimal_config):
    cfg = XrayConfig(xray_minimal_config)
    raw = cfg.to_json()
    parsed = json.loads(raw)
    assert any(i.get("tag") == "API_INBOUND" for i in parsed["inbounds"])


def test_skips_inbound_without_tag():
    config = json.dumps({
        "inbounds": [
            {"protocol": "vmess", "port": 1, "settings": {}},  # missing tag
        ]
    })
    cfg = XrayConfig(config)
    # The original tagless inbound is preserved in the config dict but never
    # reaches inbounds_by_tag (which is what the rest of marznode acts on).
    assert cfg.inbounds_by_tag == {}


def test_skips_inbound_with_unknown_protocol():
    config = json.dumps({
        "inbounds": [
            {"tag": "x", "protocol": "weird-proto", "port": 1, "settings": {}},
        ]
    })
    cfg = XrayConfig(config)
    assert cfg.inbounds_by_tag == {}
