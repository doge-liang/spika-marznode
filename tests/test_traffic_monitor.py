from datetime import datetime, timedelta, timezone

import pytest

from marznode.service.service import MarzService
from marznode.service.service_pb2 import Empty
from marznode.storage.memory import MemoryStorage
from marznode.storage.sqlite import SqliteStorage
from marznode.traffic import (
    InterfaceCounters,
    TrafficSample,
    TrafficMonitor,
    parse_proc_net_dev,
)


PROC_NET_DEV = """
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 1000       10    0    0    0     0          0         0     2000      20    0    0    0     0       0          0
  eth0: 12345     100    0    0    0     0          0         0    54321     200    0    0    0     0       0          0
 ens3: 5000       50    0    0    0     0          0         0     7000      70    0    0    0     0       0          0
"""


class FakeStream:
    def __init__(self, request):
        self.request = request
        self.sent = []

    async def recv_message(self):
        return self.request

    async def send_message(self, message):
        self.sent.append(message)


class FakeTrafficMonitor:
    def sample(self):
        return TrafficSample(
            available=True,
            sampled_at=datetime(2026, 6, 17, 12, 30, tzinfo=timezone.utc),
            rx_total=1000,
            tx_total=2000,
            rx_delta=100,
            tx_delta=50,
            rx_rate=10.5,
            tx_rate=5.25,
        )


def test_parse_proc_net_dev_reads_interface_byte_counters():
    counters = parse_proc_net_dev(PROC_NET_DEV)

    assert counters["eth0"] == InterfaceCounters(
        name="eth0", rx_bytes=12345, tx_bytes=54321
    )
    assert counters["ens3"] == InterfaceCounters(
        name="ens3", rx_bytes=5000, tx_bytes=7000
    )


def test_monitor_sums_non_loopback_interfaces_and_clamps_counter_resets():
    samples = iter(
        [
            {
                "lo": InterfaceCounters("lo", 1000, 2000),
                "eth0": InterfaceCounters("eth0", 10000, 50000),
                "ens3": InterfaceCounters("ens3", 4000, 8000),
            },
            {
                "lo": InterfaceCounters("lo", 9999, 9999),
                "eth0": InterfaceCounters("eth0", 16000, 53000),
                "ens3": InterfaceCounters("ens3", 2000, 9000),
            },
        ]
    )
    monitor = TrafficMonitor(counter_reader=lambda: next(samples))

    first = monitor.sample()
    second = monitor.sample()

    assert first.available is True
    assert first.rx_delta == 0
    assert first.tx_delta == 0
    assert second.rx_total == 18000
    assert second.tx_total == 62000
    assert second.rx_delta == 6000
    assert second.tx_delta == 4000


@pytest.mark.asyncio
async def test_memory_storage_aggregates_node_traffic_by_day_month_and_total():
    storage = MemoryStorage()
    now = datetime(2026, 6, 17, 12, 30, tzinfo=timezone.utc)
    yesterday = now - timedelta(days=1)

    await storage.record_node_traffic(now, rx_bytes=100, tx_bytes=200)
    await storage.record_node_traffic(now + timedelta(minutes=5), rx_bytes=5, tx_bytes=7)
    await storage.record_node_traffic(yesterday, rx_bytes=1000, tx_bytes=2000)

    totals = await storage.get_node_traffic_totals(now)

    assert totals.today.rx_bytes == 105
    assert totals.today.tx_bytes == 207
    assert totals.month.rx_bytes == 1105
    assert totals.month.tx_bytes == 2207
    assert totals.total.rx_bytes == 1105
    assert totals.total.tx_bytes == 2207


@pytest.mark.asyncio
async def test_sqlite_storage_persists_node_traffic_hourly_buckets(tmp_path):
    storage = SqliteStorage(str(tmp_path / "node.sqlite"))
    now = datetime(2026, 6, 17, 12, 30, tzinfo=timezone.utc)

    await storage.record_node_traffic(now, rx_bytes=100, tx_bytes=200)
    await storage.record_node_traffic(now + timedelta(minutes=5), rx_bytes=5, tx_bytes=7)

    totals = await storage.get_node_traffic_totals(now)

    assert totals.today.rx_bytes == 105
    assert totals.today.tx_bytes == 207
    assert totals.month.rx_bytes == 105
    assert totals.month.tx_bytes == 207
    assert totals.total.rx_bytes == 105
    assert totals.total.tx_bytes == 207
    if storage._db is not None:
        await storage._db.close()


@pytest.mark.asyncio
async def test_service_returns_node_traffic_stats():
    storage = MemoryStorage()
    now = datetime(2026, 6, 17, 12, 30, tzinfo=timezone.utc)
    await storage.record_node_traffic(now, rx_bytes=100, tx_bytes=50)
    service = MarzService(
        storage,
        backends={},
        traffic_monitor=FakeTrafficMonitor(),
    )
    stream = FakeStream(Empty())

    await service.FetchNodeTrafficStats(stream)

    response = stream.sent[0]
    assert response.available is True
    assert response.rx_rate == 10.5
    assert response.tx_rate == 5.25
    assert response.rx_total == 1000
    assert response.tx_total == 2000
    assert response.today.rx_bytes == 100
    assert response.today.tx_bytes == 50
    assert response.month.rx_bytes == 100
    assert response.total.tx_bytes == 50
