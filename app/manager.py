"""Scheduling. The devices share one radio, so they are polled in turn."""

import asyncio
import logging
import time
from contextlib import suppress

from .collector import DeviceCollector
from .config import Settings

log = logging.getLogger(__name__)


class CollectorManager:
    """Polls each unit in turn. They share one radio, so never in parallel."""

    def __init__(self, settings: Settings, collectors: dict[str, DeviceCollector]) -> None:
        self.settings = settings
        self.collectors = collectors
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if not self.settings.collector_ready:
            for collector in self.collectors.values():
                collector.state = "configuration required"
            return
        self._task = asyncio.create_task(self._run(), name="ecoflow-collectors")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    # An overshoot beyond this means the process was not running, and any Bluetooth
    # handle it still holds is stale.
    SUSPEND_THRESHOLD = 60.0

    async def _wait(self) -> float:
        """Sleep one poll interval, and report how far it overshot.

        A suspended process cannot run, so a sleep of 15 seconds that takes 470 is
        the clearest evidence available that the machine was away.

        An earlier version compared the monotonic and wall clocks, on the assumption
        that the monotonic one stops during sleep. It does not: on macOS it is
        `mach_absolute_time()`, which keeps counting, so the two never diverged and
        a real 470-second sleep went undetected.
        """
        requested = self.settings.poll_seconds
        before = time.time()
        await asyncio.sleep(requested)
        return (time.time() - before) - requested

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            for collector in self.collectors.values():
                if self._stop.is_set():
                    break
                if not collector.due(loop.time()):
                    continue
                try:
                    await collector.refresh()
                except Exception as error:
                    collector.failed(error, loop.time())
                else:
                    collector.succeeded()
            suspended = await self._wait()
            if suspended > self.SUSPEND_THRESHOLD:
                log.warning(
                    "poll overshot by %.0fs; the machine was suspended, so every "
                    "Bluetooth handle is stale - dropping them",
                    suspended,
                )
                # Handles held across a suspend are dead, and a unit that thinks it
                # is still connected will not advertise. Start from nothing.
                for collector in self.collectors.values():
                    await collector.reset()


