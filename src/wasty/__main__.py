"""Wasty entrypoint: build the service registry from config and run until signalled."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

from .core.bus import EventBus
from .core.config import load_config
from .core.registry import ServiceRegistry
from .core.service import Context


def build_registry(ctx: Context) -> ServiceRegistry:
    # Imported here so optional hardware deps are only touched when enabled.
    from .services.autonomy.mission import AutonomyService
    from .services.camera import CameraService
    from .services.drive import DriveService
    from .services.hotspot import HotspotService
    from .services.mediamtx import MediamtxService
    from .services.web import WebService

    registry = ServiceRegistry()
    cfg = ctx.config
    if cfg.hotspot.enabled:
        registry.add(HotspotService(ctx))
    if cfg.mediamtx.enabled:
        registry.add(MediamtxService(ctx))
    if cfg.camera.enabled:
        registry.add(CameraService(ctx))
    if cfg.drive.enabled:
        registry.add(DriveService(ctx))
    if cfg.autonomy.enabled:
        registry.add(AutonomyService(ctx))
    if cfg.web.enabled:
        registry.add(WebService(ctx))
    return registry


async def run(args: argparse.Namespace) -> None:
    config = load_config(
        Path(args.config) if args.config else None,
        mock=True if args.mock else None,
    )
    logging.basicConfig(
        level=getattr(logging, config.system.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    log = logging.getLogger("wasty")
    log.info("starting (mock=%s)", config.system.mock)

    ctx = Context(config=config, bus=EventBus())
    registry = build_registry(ctx)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await registry.start_all()
    log.info("all services up")
    await stop_event.wait()
    log.info("shutting down")
    await registry.stop_all()


def main() -> None:
    parser = argparse.ArgumentParser(prog="wasty", description="Wasty robot service")
    parser.add_argument("--config", help="path to a config overlay YAML", default=None)
    parser.add_argument("--mock", action="store_true", help="use mock hardware")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
