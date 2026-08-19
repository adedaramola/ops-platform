from __future__ import annotations

import asyncio
import time

from pydantic import SecretStr

from opsdesk.core.config import Settings
from opsdesk.traffic.generator import TrafficGenerator


class RecordingTrafficGenerator(TrafficGenerator):
    def __init__(self, settings: Settings, delay: float) -> None:
        super().__init__(settings)
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.starts: list[float] = []

    async def run_scenario(self, scenario_number: int) -> None:
        del scenario_number
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.starts.append(time.monotonic())
        try:
            await asyncio.sleep(self.delay)
        finally:
            self.active -= 1


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "traffic_enabled": True,
        "traffic_rate_per_second": 20.0,
        "traffic_concurrency": 2,
        "traffic_duration_seconds": 0.16,
        "seed_user_password": SecretStr("Demo-User-Only-99!"),
        "seed_agent_password": SecretStr("Demo-Agent-Only-99!"),
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_generator_honors_rate_duration_and_concurrency() -> None:
    async def exercise() -> None:
        generator = RecordingTrafficGenerator(_settings(), delay=0.08)
        started = time.monotonic()
        summary = await generator.run()
        elapsed = time.monotonic() - started
        assert 2 <= summary.attempted <= 5
        assert summary.succeeded == summary.attempted
        assert summary.failed == 0
        assert generator.max_active <= 2
        assert elapsed < 0.5

    asyncio.run(exercise())


def test_generator_cancels_running_scenarios_promptly() -> None:
    async def exercise() -> None:
        generator = RecordingTrafficGenerator(
            _settings(traffic_duration_seconds=10.0, traffic_rate_per_second=100.0),
            delay=5.0,
        )
        task = asyncio.create_task(generator.run())
        await asyncio.sleep(0.05)
        generator.cancel()
        summary = await asyncio.wait_for(task, timeout=0.5)
        assert summary.cancelled is True
        assert summary.attempted > 0
        assert summary.failed == 0

    asyncio.run(exercise())
