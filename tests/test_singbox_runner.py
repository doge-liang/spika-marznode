import pytest

from marznode.backends.singbox._runner import SingBoxRunner


@pytest.mark.asyncio
async def test_restart_awaits_stop_before_start(monkeypatch):
    runner = object.__new__(SingBoxRunner)
    runner.restarting = False
    events = []

    async def fake_stop(self):
        events.append("stop")

    async def fake_start(self, config_path):
        events.append(("start", config_path))

    monkeypatch.setattr(SingBoxRunner, "stop", fake_stop)
    monkeypatch.setattr(SingBoxRunner, "start", fake_start)

    await SingBoxRunner.restart(runner, "/tmp/sing-box.json")

    assert events == ["stop", ("start", "/tmp/sing-box.json")]
    assert runner.restarting is False
