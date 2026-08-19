from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

from opsdesk.core.config import get_settings
from opsdesk.observability.logging import configure_logging, get_logger
from opsdesk.traffic.generator import TrafficGenerator


async def _run() -> int:
    settings = get_settings()
    configure_logging(settings)
    generator = TrafficGenerator(settings)
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(signal_name, generator.cancel)
    summary = await generator.run()
    get_logger().info(
        "traffic.completed",
        event_name="traffic.completed",
        attempted=summary.attempted,
        succeeded=summary.succeeded,
        failed=summary.failed,
        cancelled=summary.cancelled,
        traffic_source="demo",
    )
    return 0 if summary.failed == 0 else 1


def main() -> int:
    return asyncio.run(_run())
