"""Storage backend for storing marznode data in memory"""

from datetime import timezone

from .base import BaseStorage
from ..models import NodeOutboundPolicy, User, Inbound, Outbound
from ..traffic import TrafficBytes, TrafficTotals


class MemoryStorage(BaseStorage):
    """A storage backend for marznode.
    note that this isn't fit to use in production since data gets wiped on restarts
    so if Marzneshin is down users are lost until it gets back up
    """

    def __init__(self):
        self.storage = dict(
            {
                "users": {},
                "inbounds": {},
                "user_outbounds": {},
                "node_outbound_policies": [],
                "node_traffic": {},
            }
        )

    async def list_users(self, user_id: int | None = None) -> list[User] | User | None:
        if user_id:
            return self.storage["users"].get(user_id)
        return list(self.storage["users"].values())

    async def list_inbounds(
        self, tag: list[str] | str | None = None, include_users: bool = False
    ) -> list[Inbound] | Inbound | None:
        if tag is not None:
            if isinstance(tag, str):
                return self.storage["inbounds"][tag]
            return [
                self.storage["inbounds"][t]
                for t in tag
                if t in self.storage["inbounds"]
            ]
            # return [i for i in self.storage["inbounds"].values() if i.tag in tag]
        return list(self.storage["inbounds"].values())

    async def list_inbound_users(self, tag: str) -> list[User]:
        users = []
        for user in self.storage["users"].values():
            for inbound in user.inbounds:
                if inbound.tag == tag:
                    users.append(user)
                    break
        return users

    async def remove_user(self, user: User) -> None:
        del self.storage["users"][user.id]

    async def update_user_inbounds(self, user: User, inbounds: list[Inbound]) -> None:
        if self.storage["users"].get(user.id):
            self.storage["users"][user.id].inbounds = inbounds
        user.inbounds = inbounds
        self.storage["users"][user.id] = user

    def register_inbound(self, inbound: Inbound) -> None:
        self.storage["inbounds"][inbound.tag] = inbound

    def remove_inbound(self, inbound: Inbound | str) -> None:
        tag = inbound if isinstance(inbound, str) else inbound.tag
        if tag in self.storage["inbounds"]:
            self.storage["inbounds"].pop(tag)
        for user_id, user in self.storage["users"].items():
            user.inbounds = list(filter(lambda inb: inb.tag != tag, user.inbounds))

    async def flush_users(self):
        self.storage["users"] = {}
        self.storage["user_outbounds"] = {}

    async def update_user_outbounds(
        self, user: User, outbounds: list[Outbound]
    ) -> None:
        if outbounds:
            self.storage["user_outbounds"][user.id] = list(outbounds)
        else:
            self.storage["user_outbounds"].pop(user.id, None)
        if self.storage["users"].get(user.id):
            self.storage["users"][user.id].outbounds = list(outbounds)
        user.outbounds = list(outbounds)

    async def list_user_outbounds(self, user_id: int) -> list[Outbound]:
        return list(self.storage["user_outbounds"].get(user_id, []))

    async def replace_node_outbound_policies(
        self, policies: list[NodeOutboundPolicy]
    ) -> None:
        self.storage["node_outbound_policies"] = list(policies)

    async def list_node_outbound_policies(self) -> list[NodeOutboundPolicy]:
        return list(self.storage["node_outbound_policies"])

    @staticmethod
    def _hour_bucket(dt):
        return (
            dt.astimezone(timezone.utc)
            .replace(minute=0, second=0, microsecond=0)
        )

    async def record_node_traffic(
        self, created_at, rx_bytes: int, tx_bytes: int
    ) -> None:
        bucket = self._hour_bucket(created_at)
        current = self.storage["node_traffic"].setdefault(
            bucket, TrafficBytes()
        )
        self.storage["node_traffic"][bucket] = TrafficBytes(
            rx_bytes=current.rx_bytes + rx_bytes,
            tx_bytes=current.tx_bytes + tx_bytes,
        )

    async def get_node_traffic_totals(self, now) -> TrafficTotals:
        now = now.astimezone(timezone.utc)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)

        def sum_since(start):
            rx = tx = 0
            for bucket, usage in self.storage["node_traffic"].items():
                if bucket >= start:
                    rx += usage.rx_bytes
                    tx += usage.tx_bytes
            return TrafficBytes(rx_bytes=rx, tx_bytes=tx)

        total_rx = sum(
            usage.rx_bytes for usage in self.storage["node_traffic"].values()
        )
        total_tx = sum(
            usage.tx_bytes for usage in self.storage["node_traffic"].values()
        )
        return TrafficTotals(
            today=sum_since(day_start),
            month=sum_since(month_start),
            total=TrafficBytes(rx_bytes=total_rx, tx_bytes=total_tx),
        )
