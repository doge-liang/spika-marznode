import json
from collections import defaultdict

import commentjson

from marznode.config import XRAY_EXECUTABLE_PATH, XRAY_VLESS_REALITY_FLOW, DEBUG
from ._utils import get_x25519
try:
    from ...models import Inbound, NodeOutboundPolicy
except ImportError:
    from ...models import Inbound

    NodeOutboundPolicy = object
from ...storage import BaseStorage

transport_map = defaultdict(
    lambda: "tcp",
    {
        "tcp": "tcp",
        "raw": "tcp",
        "splithttp": "splithttp",
        "xhttp": "splithttp",
        "grpc": "grpc",
        "kcp": "kcp",
        "mkcp": "kcp",
        "h2": "http",
        "h3": "http",
        "http": "http",
        "ws": "ws",
        "websocket": "ws",
        "httpupgrade": "httpupgrade",
        "quic": "quic",
    },
)

forced_policies = {
  "levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True}},
  "system": {
    "statsInboundDownlink": False,
    "statsInboundUplink": False,
    "statsOutboundDownlink": True,
    "statsOutboundUplink": True
  }
}

def first_non_empty(values, default=""):
    """Prefer a real Reality shortId over the legacy empty compatibility slot."""
    if isinstance(values, str):
        return values or default
    for value in values or []:
        if value:
            return value
    if values:
        return values[0] or default
    return default


def listify(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def is_broad_inbound_route(rule):
    if "user" in rule or "inboundTag" not in rule:
        return False
    for scoped_key in ("domain", "ip", "protocol", "port", "network", "source"):
        if rule.get(scoped_key):
            return False
    return True


def merge_dicts(a, b): # B overrides A dict
    for key, value in b.items():
        if isinstance(value, dict) and key in a and isinstance(a[key], dict):
            merge_dicts(a[key], value)
        else:
            a[key] = value
    return a

class XrayConfig(dict):
    def __init__(
        self,
        config: str,
        api_host: str = "127.0.0.1",
        api_port: int = 8080,
    ):
        try:
            # considering string as json
            config = commentjson.loads(config)
        except (json.JSONDecodeError, ValueError):
            # considering string as file path
            with open(config) as file:
                config = commentjson.loads(file.read())

        self.api_host = api_host
        self.api_port = api_port

        super().__init__(config)

        self.inbounds = []
        self.inbounds_by_tag = {}
        # self._fallbacks_inbound = self.get_inbound(XRAY_FALLBACKS_INBOUND_TAG)
        self._resolve_inbounds()

        self._apply_api()

    def _apply_api(self):
        self["api"] = {
            "services": ["HandlerService", "StatsService", "LoggerService"],
            "tag": "API",
        }
        self["stats"] = {}
        if self.get("policy"):
            self["policy"] = merge_dicts(self.get("policy"), forced_policies)
        else:
            self["policy"] = forced_policies
        inbound = {
            "listen": self.api_host,
            "port": self.api_port,
            "protocol": "dokodemo-door",
            "settings": {"address": self.api_host},
            "tag": "API_INBOUND",
        }
        if "inbounds" not in self:
            self["inbounds"] = []
        self["inbounds"].insert(0, inbound)

        rule = {"inboundTag": ["API_INBOUND"], "outboundTag": "API", "type": "field"}

        if "routing" not in self:
            self["routing"] = {"rules": []}
        self["routing"]["rules"].insert(0, rule)

    def _resolve_inbounds(self):
        for inbound in self["inbounds"]:
            if (
                inbound.get("protocol", "").lower()
                not in {
                    "vmess",
                    "trojan",
                    "vless",
                    "shadowsocks",
                }
                or "tag" not in inbound
            ):
                continue

            settings = {
                "tag": inbound["tag"],
                "protocol": inbound["protocol"],
                "port": inbound.get("port"),
                "network": "tcp",
                "tls": "none",
                "sni": [],
                "host": [],
                "path": None,
                "header_type": None,
                "flow": None,
                "is_fallback": False,
            }

            # port settings, TODO: fix port and stream settings for fallbacks

            # stream settings
            if stream := inbound.get("streamSettings"):
                net = stream.get("network", "tcp")
                net_settings = stream.get(f"{net}Settings", {})
                security = stream.get("security")
                tls_settings = stream.get(f"{security}Settings")

                settings["network"] = transport_map[net]

                if security == "tls":
                    settings["tls"] = "tls"
                elif security == "reality":
                    settings["fp"] = "chrome"
                    settings["tls"] = "reality"
                    settings["sni"] = tls_settings.get("serverNames", [])
                    if inbound["protocol"] == "vless" and transport_map[net] == "tcp":
                        settings["flow"] = XRAY_VLESS_REALITY_FLOW

                    pvk = tls_settings.get("privateKey")

                    x25519 = get_x25519(XRAY_EXECUTABLE_PATH, pvk)
                    settings["pbk"] = x25519["public_key"]

                    settings["sid"] = first_non_empty(tls_settings.get("shortIds"))

                if net in ["tcp", "raw"]:
                    header = net_settings.get("header", {})
                    request = header.get("request", {})
                    path = request.get("path")
                    host = request.get("headers", {}).get("Host")

                    settings["header_type"] = header.get("type")

                    if path and isinstance(path, list):
                        settings["path"] = path[0]

                    if host and isinstance(host, list):
                        settings["host"] = host

                elif net in ["ws", "websocket", "httpupgrade", "splithttp", "xhttp"]:
                    settings["path"] = net_settings.get("path")
                    settings["host"] = listify(net_settings.get("host"))

                elif net == "grpc":
                    settings["path"] = net_settings.get("serviceName")

                elif net in ["kcp", "mkcp"]:
                    settings["path"] = net_settings.get("seed")
                    settings["header_type"] = net_settings.get("header", {}).get("type")

                elif net == "quic":
                    settings["host"] = net_settings.get("security")
                    settings["path"] = net_settings.get("key")
                    settings["header_type"] = net_settings.get("header", {}).get("type")

                elif net == "http":
                    settings["path"] = net_settings.get("path")
                    settings["host"] = net_settings.get("host")

            if inbound["protocol"] == "shadowsocks":
                settings["network"] = None

            self.inbounds.append(settings)
            self.inbounds_by_tag[inbound["tag"]] = settings

    def register_inbounds(self, storage: BaseStorage):
        for inbound in self.list_inbounds():
            storage.register_inbound(inbound)

    def list_inbounds(self) -> list[Inbound]:
        return [
            Inbound(tag=i["tag"], protocol=i["protocol"], config=i)
            for i in self.inbounds_by_tag.values()
        ]

    def apply_user_outbounds(self, users: list) -> None:
        """Inject per-user upstream outbounds + routing rules from storage.

        Each Outbound becomes an xray outbound tagged ``res-{username}`` and a
        routing rule binding ``{id}.{username}`` (optionally scoped to the
        Outbound's inbound_tags) to it. xray can't hot-add outbounds via the
        HandlerService API, so this must run on the in-memory config before
        the xray process starts.
        """
        self.setdefault("outbounds", [])
        routing = self.setdefault("routing", {})
        rules = routing.setdefault("rules", [])
        existing_tags = {o.get("tag") for o in self["outbounds"]}
        existing_route_keys = {
            (tuple(rule.get("user", [])), rule.get("outboundTag"))
            for rule in rules
        }

        for user in users:
            for ob in getattr(user, "outbounds", []) or []:
                tag = f"res-{user.username}"
                if tag not in existing_tags:
                    server = {"address": ob.address, "port": ob.port}
                    if ob.username:
                        server["users"] = [
                            {"user": ob.username, "pass": ob.password or ""}
                        ]
                    self["outbounds"].append(
                        {
                            "tag": tag,
                            "protocol": ob.protocol,
                            "settings": {"servers": [server]},
                        }
                    )
                    existing_tags.add(tag)

                rule = {
                    "type": "field",
                    "user": [f"{user.id}.{user.username}"],
                    "outboundTag": tag,
                }
                if ob.inbound_tags:
                    rule["inboundTag"] = list(ob.inbound_tags)
                route_key = (tuple(rule["user"]), tag)
                if route_key not in existing_route_keys:
                    insert_at = next(
                        (
                            idx
                            for idx, existing_rule in enumerate(rules)
                            if is_broad_inbound_route(existing_rule)
                        ),
                        len(rules),
                    )
                    rules.insert(insert_at, rule)
                    existing_route_keys.add(route_key)

    @staticmethod
    def _node_policy_tag(policy: NodeOutboundPolicy) -> str:
        return f"NODE_POLICY_{policy.id}"

    @staticmethod
    def _policy_rule_index(rules: list[dict]) -> int:
        """Place policy rules before broad catch-all routing rules."""
        for index, rule in enumerate(rules):
            has_match = any(
                key in rule
                for key in ("inboundTag", "user", "domain", "ip", "port")
            )
            if not has_match and (
                rule.get("outboundTag") or rule.get("balancerTag")
            ):
                return index
        return len(rules)

    def apply_node_outbound_policies(
        self, policies: list[NodeOutboundPolicy]
    ) -> None:
        """Inject node-level upstream outbounds + inbound-tag routing rules."""
        self.setdefault("outbounds", [])
        routing = self.setdefault("routing", {})
        rules = routing.setdefault("rules", [])
        existing_tags = {o.get("tag") for o in self["outbounds"]}
        existing_route_keys = {
            (tuple(rule.get("inboundTag", [])), rule.get("outboundTag"))
            for rule in rules
        }

        for policy in policies:
            tag = self._node_policy_tag(policy)
            if tag not in existing_tags:
                server = {"address": policy.address, "port": policy.port}
                if policy.username:
                    server["users"] = [
                        {"user": policy.username, "pass": policy.password or ""}
                    ]
                self["outbounds"].append(
                    {
                        "tag": tag,
                        "protocol": policy.protocol,
                        "settings": {"servers": [server]},
                    }
                )
                existing_tags.add(tag)

            rule = {
                "type": "field",
                "inboundTag": list(policy.inbound_tags or []),
                "outboundTag": tag,
            }
            route_key = (tuple(rule["inboundTag"]), tag)
            if route_key not in existing_route_keys:
                rules.insert(self._policy_rule_index(rules), rule)
                existing_route_keys.add(route_key)

    def to_json(self, **json_kwargs):
        if DEBUG:
            with open('xray_config_debug.json', 'w') as f:
                f.write(json.dumps(self, indent=4))
        return json.dumps(self, **json_kwargs)
