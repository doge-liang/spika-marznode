import asyncio

import pytest

import marznode.backends.xray.xray_backend as xray_backend_module
from marznode.backends.xray.xray_backend import XrayBackend


class _Runner:
    def __init__(self, running=False):
        self.running = running


def _backend(running=False):
    backend = object.__new__(XrayBackend)
    backend._runner = _Runner(running=running)
    backend._restart_lock = asyncio.Lock()
    backend._auto_restart_lock = asyncio.Lock()
    return backend


@pytest.mark.asyncio
async def test_recover_stopped_runner_restarts_even_without_stop_event(monkeypatch):
    backend = _backend(running=False)
    calls = []

    async def fake_start(self):
        calls.append("start")
        self._runner.running = True

    monkeypatch.setattr(xray_backend_module, "XRAY_RESTART_ON_FAILURE", True)
    monkeypatch.setattr(xray_backend_module, "XRAY_RESTART_ON_FAILURE_INTERVAL", 0)
    monkeypatch.setattr(XrayBackend, "start", fake_start)

    await XrayBackend._recover_stopped_runner(backend, "poll")

    assert calls == ["start"]
    assert backend._runner.running is True


@pytest.mark.asyncio
async def test_recover_stopped_runner_does_not_restart_running_core(monkeypatch):
    backend = _backend(running=True)
    calls = []

    async def fake_start(self):
        calls.append("start")

    monkeypatch.setattr(XrayBackend, "start", fake_start)

    await XrayBackend._recover_stopped_runner(backend, "poll")

    assert calls == []


@pytest.mark.asyncio
async def test_recover_stopped_runner_does_not_restart_after_explicit_stop(
    monkeypatch,
):
    backend = _backend(running=False)
    backend._started_once = False
    calls = []

    async def fake_start(self):
        calls.append("start")

    monkeypatch.setattr(XrayBackend, "start", fake_start)

    await XrayBackend._recover_stopped_runner(backend, "process exit")

    assert calls == []


@pytest.mark.asyncio
async def test_recover_stopped_runner_keeps_watchdog_alive_after_start_failure(
    monkeypatch,
):
    backend = _backend(running=False)

    async def fake_start(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(xray_backend_module, "XRAY_RESTART_ON_FAILURE", True)
    monkeypatch.setattr(xray_backend_module, "XRAY_RESTART_ON_FAILURE_INTERVAL", 0)
    monkeypatch.setattr(XrayBackend, "start", fake_start)

    await XrayBackend._recover_stopped_runner(backend, "poll")
