from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InterfaceCounters:
    name: str
    rx_bytes: int
    tx_bytes: int


@dataclass(frozen=True)
class TrafficBytes:
    rx_bytes: int = 0
    tx_bytes: int = 0


@dataclass(frozen=True)
class TrafficTotals:
    today: TrafficBytes
    month: TrafficBytes
    total: TrafficBytes


@dataclass(frozen=True)
class TrafficSample:
    available: bool
    sampled_at: datetime
    rx_total: int = 0
    tx_total: int = 0
    rx_delta: int = 0
    tx_delta: int = 0
    rx_rate: float = 0.0
    tx_rate: float = 0.0


def parse_proc_net_dev(content: str) -> dict[str, InterfaceCounters]:
    counters: dict[str, InterfaceCounters] = {}
    for line in content.splitlines():
        if ":" not in line:
            continue
        name, values = line.split(":", 1)
        parts = values.split()
        if len(parts) < 16:
            continue
        iface = name.strip()
        counters[iface] = InterfaceCounters(
            name=iface,
            rx_bytes=int(parts[0]),
            tx_bytes=int(parts[8]),
        )
    return counters


def read_proc_net_dev(path: str = "/proc/net/dev") -> dict[str, InterfaceCounters]:
    with open(path, encoding="utf-8") as fh:
        return parse_proc_net_dev(fh.read())


class TrafficMonitor:
    def __init__(
        self,
        counter_reader: Callable[[], dict[str, InterfaceCounters]] = read_proc_net_dev,
        interfaces: list[str] | None = None,
    ):
        self._counter_reader = counter_reader
        self._interfaces = set(interfaces or [])
        self._previous: tuple[dict[str, InterfaceCounters], float] | None = None
        self.latest_sample: TrafficSample | None = None

    def _select_counters(
        self, counters: dict[str, InterfaceCounters]
    ) -> list[InterfaceCounters]:
        if self._interfaces:
            return [
                counters[name]
                for name in sorted(self._interfaces)
                if name in counters
            ]
        return [
            counter
            for name, counter in counters.items()
            if name != "lo" and not name.startswith("lo:")
        ]

    def sample(self) -> TrafficSample:
        sampled_at = datetime.now(timezone.utc)
        try:
            selected = self._select_counters(self._counter_reader())
        except OSError:
            self._previous = None
            self.latest_sample = TrafficSample(
                available=False, sampled_at=sampled_at
            )
            return self.latest_sample

        rx_total = sum(counter.rx_bytes for counter in selected)
        tx_total = sum(counter.tx_bytes for counter in selected)
        now = monotonic()

        selected_by_name = {counter.name: counter for counter in selected}

        if self._previous is None:
            rx_delta = 0
            tx_delta = 0
            elapsed = 0.0
        else:
            previous, prev_time = self._previous
            rx_delta = sum(
                max(counter.rx_bytes - previous[counter.name].rx_bytes, 0)
                for counter in selected
                if counter.name in previous
            )
            tx_delta = sum(
                max(counter.tx_bytes - previous[counter.name].tx_bytes, 0)
                for counter in selected
                if counter.name in previous
            )
            elapsed = max(now - prev_time, 0.0)

        self._previous = (selected_by_name, now)
        self.latest_sample = TrafficSample(
            available=True,
            sampled_at=sampled_at,
            rx_total=rx_total,
            tx_total=tx_total,
            rx_delta=rx_delta,
            tx_delta=tx_delta,
            rx_rate=(rx_delta / elapsed if elapsed else 0.0),
            tx_rate=(tx_delta / elapsed if elapsed else 0.0),
        )
        return self.latest_sample


async def run_traffic_monitor(storage, monitor: TrafficMonitor, interval: int):
    while True:
        try:
            sample = monitor.sample()
            if sample.available and (sample.rx_delta or sample.tx_delta):
                await storage.record_node_traffic(
                    sample.sampled_at,
                    rx_bytes=sample.rx_delta,
                    tx_bytes=sample.tx_delta,
                )
        except Exception:
            logger.exception("node traffic monitor sample failed")
        await asyncio.sleep(interval)
