"""Service registry: dependency-ordered startup, crash restart with backoff."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .service import Service, ServiceState

log = logging.getLogger(__name__)

RESTART_BACKOFF_INITIAL = 1.0
RESTART_BACKOFF_MAX = 30.0


class ServiceRegistry:
    def __init__(self) -> None:
        self._services: dict[str, Service] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._start_order: list[str] = []

    def add(self, service: Service) -> None:
        if service.name in self._services:
            raise ValueError(f"duplicate service name: {service.name}")
        self._services[service.name] = service
        service.ctx.registry = self

    def get(self, name: str) -> Service | None:
        return self._services.get(name)

    def _topo_order(self) -> list[str]:
        order: list[str] = []
        visiting: set[str] = set()

        def visit(name: str) -> None:
            if name in order:
                return
            if name in visiting:
                raise ValueError(f"dependency cycle involving {name}")
            visiting.add(name)
            svc = self._services.get(name)
            if svc is not None:
                for dep in svc.depends_on:
                    if dep in self._services:
                        visit(dep)
            visiting.discard(name)
            if name in self._services:
                order.append(name)

        for name in self._services:
            visit(name)
        return order

    async def start_all(self) -> None:
        self._start_order = self._topo_order()
        for name in self._start_order:
            svc = self._services[name]
            svc.state = ServiceState.STARTING
            try:
                await svc.start()
            except Exception:
                svc.state = ServiceState.FAILED
                log.exception("service %s failed to start", name)
                continue
            svc.state = ServiceState.RUNNING
            self._tasks[name] = asyncio.create_task(
                self._supervise(svc), name=f"svc:{name}"
            )
            log.info("service %s started", name)

    async def _supervise(self, svc: Service) -> None:
        """Run the service loop; on crash, stop/start it again with backoff."""
        backoff = RESTART_BACKOFF_INITIAL
        while True:
            try:
                await svc.run()
                return  # clean exit
            except asyncio.CancelledError:
                raise
            except Exception:
                svc.state = ServiceState.RESTARTING
                svc.log.exception("crashed; restarting in %.0fs", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RESTART_BACKOFF_MAX)
                try:
                    await svc.stop()
                    await svc.start()
                    svc.state = ServiceState.RUNNING
                except Exception:
                    svc.state = ServiceState.FAILED
                    svc.log.exception("restart failed; will retry")

    async def stop_all(self) -> None:
        for name in reversed(self._start_order):
            task = self._tasks.pop(name, None)
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            svc = self._services[name]
            try:
                await svc.stop()
            except Exception:
                log.exception("service %s failed to stop cleanly", name)
            svc.state = ServiceState.STOPPED
            log.info("service %s stopped", name)

    def status(self) -> dict[str, Any]:
        return {
            name: {"state": svc.state.value, **svc.status()}
            for name, svc in self._services.items()
        }

    def ui_panels(self) -> list[str]:
        panels: list[str] = []
        for name in self._start_order or self._services:
            svc = self._services[name]
            if svc.state in (ServiceState.RUNNING, ServiceState.RESTARTING):
                for panel in svc.ui_panels:
                    if panel not in panels:
                        panels.append(panel)
        return panels
