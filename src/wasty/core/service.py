"""Service base class: lifecycle, dependencies, health, UI capability advertising."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .bus import EventBus
    from .config import Config
    from .registry import ServiceRegistry


@dataclass
class Context:
    """Shared handles every service receives."""

    config: Config
    bus: EventBus
    registry: ServiceRegistry = field(default=None)  # set by the registry


class ServiceState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    RESTARTING = "restarting"
    FAILED = "failed"


class Service:
    """Base class for all Wasty services.

    Subclasses override:
      - start(): acquire resources, subscribe to topics
      - run():   optional long-running loop (supervised, restarted on crash)
      - stop():  release resources
      - status(): service-specific status dict for /api/status
    """

    name: str = "service"
    depends_on: Sequence[str] = ()
    ui_panels: Sequence[str] = ()

    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.log = logging.getLogger(f"wasty.{self.name}")
        self.state = ServiceState.STOPPED

    async def start(self) -> None:  # noqa: B027
        pass

    async def run(self) -> None:
        # Default: nothing to supervise; sleep until cancelled.
        await asyncio.Event().wait()

    async def stop(self) -> None:  # noqa: B027
        pass

    def status(self) -> dict[str, Any]:
        return {}
