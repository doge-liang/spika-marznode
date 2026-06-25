import json

from marznode.backends.singbox import _config as singbox_config
from marznode.backends.singbox._config import SingBoxConfig
from marznode.backends.xray import _config as xray_config
from marznode.backends.xray import _utils as xray_utils
from marznode.backends.xray._config import XrayConfig


def test_get_x25519_parses_xray_26_output(monkeypatch):
    def fake_check_output(cmd, stderr):
        assert cmd == ["/usr/local/bin/xray", "x25519", "-i", "private"]
        assert stderr == xray_utils.subprocess.STDOUT
        return (
            b"PrivateKey: private\n"
            b"Password (PublicKey): public\n"
            b"Hash32: hash\n"
        )

    monkeypatch.setattr(xray_utils.subprocess, "check_output", fake_check_output)

    assert xray_utils.get_x25519("/usr/local/bin/xray", "private") == {
        "private_key": "private",
        "public_key": "public",
    }


def test_xray_reality_prefers_non_empty_short_id(monkeypatch):
    monkeypatch.setattr(
        xray_config, "get_x25519", lambda *_args, **_kwargs: {"public_key": "pbk"}
    )

    config = XrayConfig(
        json.dumps(
            {
                "inbounds": [
                    {
                        "tag": "reality-in",
                        "port": 443,
                        "protocol": "vless",
                        "settings": {"clients": [], "decryption": "none"},
                        "streamSettings": {
                            "network": "tcp",
                            "security": "reality",
                            "realitySettings": {
                                "serverNames": ["example.com"],
                                "privateKey": "private",
                                "shortIds": ["", "0123456789abcdef"],
                            },
                        },
                    }
                ],
                "outbounds": [{"tag": "DIRECT", "protocol": "freedom"}],
                "routing": {"rules": []},
            }
        )
    )

    assert config.list_inbounds()[0].config["sid"] == "0123456789abcdef"


def test_xray_http_transport_host_is_normalized_to_list():
    config = XrayConfig(
        json.dumps(
            {
                "inbounds": [
                    {
                        "tag": "xhttp-in",
                        "port": 8443,
                        "protocol": "vless",
                        "settings": {"clients": [], "decryption": "none"},
                        "streamSettings": {
                            "network": "xhttp",
                            "security": "tls",
                            "xhttpSettings": {
                                "path": "/spika-xhttp",
                                "host": "node1.s-pika.com",
                            },
                        },
                    }
                ],
                "outbounds": [{"tag": "DIRECT", "protocol": "freedom"}],
                "routing": {"rules": []},
            }
        )
    )

    inbound = config.list_inbounds()[0].config

    assert inbound["network"] == "splithttp"
    assert inbound["host"] == ["node1.s-pika.com"]


def test_singbox_reality_prefers_non_empty_short_id(monkeypatch):
    monkeypatch.setattr(
        singbox_config, "get_x25519", lambda *_args, **_kwargs: {"public_key": "pbk"}
    )

    config = SingBoxConfig(
        json.dumps(
            {
                "inbounds": [
                    {
                        "type": "vless",
                        "tag": "reality-in",
                        "listen_port": 443,
                        "users": [],
                        "tls": {
                            "enabled": True,
                            "reality": {
                                "enabled": True,
                                "private_key": "private",
                                "short_id": ["", "0123456789abcdef"],
                            },
                        },
                    }
                ],
                "outbounds": [{"type": "direct", "tag": "direct"}],
            }
        )
    )

    assert config.list_inbounds()[0].config["sid"] == "0123456789abcdef"
