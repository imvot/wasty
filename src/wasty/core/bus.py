"""In-process async pub/sub event bus.

Queues are bounded and drop the oldest message when full, so a slow
subscriber can never stall a publisher and always sees the freshest data.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)

# Topic names
DRIVE_INTENT = "drive.intent"
DRIVE_STATE = "drive.state"
SAFETY_ESTOP = "safety.estop"
VISION_DETECTIONS = "vision.detections"
MISSION_COMMAND = "mission.command"
MISSION_STATE = "mission.state"
RECORDING_STATE = "recording.state"


class Subscription:
    def __init__(self, bus: EventBus, topic: str, maxsize: int):
        self._bus = bus
        self.topic = topic
        self.queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=maxsize)

    async def get(self) -> Any:
        return await self.queue.get()

    def drain(self) -> list[Any]:
        """Return all currently queued messages without blocking."""
        items = []
        while True:
            try:
                items.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                return items

    def latest(self) -> Any | None:
        items = self.drain()
        return items[-1] if items else None

    def close(self) -> None:
        self._bus._unsubscribe(self)

    def __aiter__(self):
        return self

    async def __anext__(self) -> Any:
        return await self.queue.get()


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Subscription]] = {}

    def subscribe(self, topic: str, maxsize: int = 16) -> Subscription:
        sub = Subscription(self, topic, maxsize)
        self._subs.setdefault(topic, []).append(sub)
        return sub

    def _unsubscribe(self, sub: Subscription) -> None:
        subs = self._subs.get(sub.topic, [])
        if sub in subs:
            subs.remove(sub)

    def publish(self, topic: str, message: Any) -> None:
        for sub in self._subs.get(topic, []):
            queue = sub.queue
            if queue.full():
                try:
                    queue.get_nowait()  # drop oldest, keep latest
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:  # pragma: no cover - defensive
                log.warning("dropped message on %s", topic)
