"""Standalone background worker entrypoint.

The FastAPI web process still starts workers by default for backward-compatible
single-service deployments. Set BACKGROUND_WORKERS_ENABLED=false on the web
service and run this module from a separate Railway worker service when splitting
API traffic from scanners.
"""

import asyncio
import logging
import signal

from main import run_background_workers

logger = logging.getLogger("trading_signal.worker")


async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    worker_task = asyncio.create_task(run_background_workers())
    logger.info("獨立背景 worker 已啟動")
    try:
        await stop_event.wait()
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        logger.info("獨立背景 worker 已關閉")


if __name__ == "__main__":
    asyncio.run(main())
