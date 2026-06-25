import json

import pytest

from marznode.backends.singbox._config import SingBoxConfig
from marznode.backends.xray._config import XrayConfig
from marznode.models import NodeOutboundPolicy
from marznode.storage.sqlite import SqliteStorage


async def _close(storage: SqliteStorage) -> None:
    if storage._db is not None:
        await storage._db.close()
        storage._db = None


def _policy(**overrides) -> NodeOutboundPolicy:
    fields = dict(
        id=17,
        name="dmit-215-node-exit",
        protocol="http",
        address="163.123.200.59",
        port=6344,
        username="xmtjqdsz",
        password="4f4vke1m1gpj",
        inbound_tags=["VLESS Reality Vision DMIT"],
    )
    fields.update(overrides)
    return NodeOutboundPolicy(**fields)


@pytest.mark.asyncio
async def test_sqlite_storage_round_trips_node_outbound_policies(tmp_path):
    storage = SqliteStorage(str(tmp_path / "marznode.db"))
    policies = [
        _policy(),
        _policy(
            id=18,
            name="socks-exit",
            protocol="socks",
            address="198.51.100.8",
            port=1080,
            username=None,
            password=None,
            inbound_tags=["VLESS WS CF", "Trojan WS CF"],
        ),
    ]

    await storage.replace_node_outbound_policies(policies)
    await _close(storage)

    reopened = SqliteStorage(str(tmp_path / "marznode.db"))
    restored = await reopened.list_node_outbound_policies()

    assert [policy.model_dump() for policy in restored] == [
        policy.model_dump() for policy in policies
    ]
    await reopened.replace_node_outbound_policies([])
    assert await reopened.list_node_outbound_policies() == []
    await _close(reopened)


def test_xray_node_outbound_policy_generation_preserves_direct():
    config = XrayConfig(
        json.dumps(
            {
                "inbounds": [],
                "outbounds": [{"tag": "DIRECT", "protocol": "freedom"}],
                "routing": {"rules": []},
            }
        )
    )

    config.apply_node_outbound_policies([_policy()])

    assert config["outbounds"][0]["tag"] == "DIRECT"
    outbound = next(
        o for o in config["outbounds"] if o["tag"] == "NODE_POLICY_17"
    )
    assert outbound == {
        "tag": "NODE_POLICY_17",
        "protocol": "http",
        "settings": {
            "servers": [
                {
                    "address": "163.123.200.59",
                    "port": 6344,
                    "users": [
                        {"user": "xmtjqdsz", "pass": "4f4vke1m1gpj"}
                    ],
                }
            ]
        },
    }
    rule = next(
        r
        for r in config["routing"]["rules"]
        if r.get("outboundTag") == "NODE_POLICY_17"
    )
    assert rule == {
        "type": "field",
        "inboundTag": ["VLESS Reality Vision DMIT"],
        "outboundTag": "NODE_POLICY_17",
    }


def test_singbox_node_outbound_policy_generation():
    config = SingBoxConfig(
        json.dumps(
            {
                "inbounds": [],
                "outbounds": [{"type": "direct", "tag": "DIRECT"}],
                "route": {"rules": []},
            }
        )
    )

    config.apply_node_outbound_policies([_policy()])

    outbound = next(
        o for o in config["outbounds"] if o["tag"] == "NODE_POLICY_17"
    )
    assert outbound == {
        "type": "http",
        "tag": "NODE_POLICY_17",
        "server": "163.123.200.59",
        "server_port": 6344,
        "username": "xmtjqdsz",
        "password": "4f4vke1m1gpj",
    }
    assert config["route"]["rules"] == [
        {
            "inbound": ["VLESS Reality Vision DMIT"],
            "outbound": "NODE_POLICY_17",
        }
    ]
