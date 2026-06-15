import json

from marznode.backends.xray._config import XrayConfig
from marznode.models import Outbound, User


def _config(extra_outbounds=None) -> XrayConfig:
    return XrayConfig(
        json.dumps(
            {
                "inbounds": [],
                "outbounds": [
                    {"tag": "DIRECT", "protocol": "freedom"},
                    *(extra_outbounds or []),
                ],
                "routing": {"rules": []},
            }
        )
    )


def test_apply_user_outbounds_preserves_direct_and_adds_scoped_route():
    config = _config()
    user = User(
        id=7,
        username="alice",
        key="k-alice",
        outbounds=[
            Outbound(
                protocol="socks",
                address="198.51.100.10",
                port=1080,
                username="up-user",
                password="up-pass",
                inbound_tags=["res-in"],
            )
        ],
    )

    config.apply_user_outbounds([user])

    assert config["outbounds"][0]["tag"] == "DIRECT"
    res_outbound = next(o for o in config["outbounds"] if o["tag"] == "res-alice")
    assert res_outbound == {
        "tag": "res-alice",
        "protocol": "socks",
        "settings": {
            "servers": [
                {
                    "address": "198.51.100.10",
                    "port": 1080,
                    "users": [{"user": "up-user", "pass": "up-pass"}],
                }
            ]
        },
    }
    rule = next(
        r for r in config["routing"]["rules"] if r.get("outboundTag") == "res-alice"
    )
    assert rule["user"] == ["7.alice"]
    assert rule["inboundTag"] == ["res-in"]


def test_apply_user_outbounds_does_not_duplicate_existing_res_tag():
    config = _config(
        [
            {
                "tag": "res-alice",
                "protocol": "socks",
                "settings": {"servers": [{"address": "old", "port": 1}]},
            }
        ]
    )
    user = User(
        id=7,
        username="alice",
        key="k-alice",
        outbounds=[
            Outbound(
                protocol="socks",
                address="198.51.100.10",
                port=1080,
            )
        ],
    )

    config.apply_user_outbounds([user])

    res_outbounds = [o for o in config["outbounds"] if o["tag"] == "res-alice"]
    assert len(res_outbounds) == 1
    assert res_outbounds[0]["settings"]["servers"] == [{"address": "old", "port": 1}]


def test_apply_user_outbounds_keeps_existing_res_tag_but_adds_missing_route():
    config = _config(
        [
            {
                "tag": "res-alice",
                "protocol": "socks",
                "settings": {"servers": [{"address": "old", "port": 1}]},
            }
        ]
    )
    user = User(
        id=7,
        username="alice",
        key="k-alice",
        outbounds=[
            Outbound(
                protocol="socks",
                address="198.51.100.10",
                port=1080,
                inbound_tags=["res-in"],
            )
        ],
    )

    config.apply_user_outbounds([user])

    route_rules = [
        r for r in config["routing"]["rules"] if r.get("outboundTag") == "res-alice"
    ]
    assert route_rules == [
        {
            "type": "field",
            "user": ["7.alice"],
            "outboundTag": "res-alice",
            "inboundTag": ["res-in"],
        }
    ]
