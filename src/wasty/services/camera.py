"""CameraService: owns the camera, feeds MediaMTX (RTSP) and the vision tap."""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from ..core.service import Service
from ..hw.camera import create_camera_hw


class CameraService(Service):
    name = "camera"
    depends_on = ("mediamtx",)
    ui_panels = ("video",)

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cfg = ctx.config.camera
        self.hw = None

    async def start(self) -> None:
        mtx_cfg = self.ctx.config.mediamtx
        rtsp_url = f"rtsp://127.0.0.1:{mtx_cfg.rtsp_port}/{mtx_cfg.stream_name}"
        self.hw = create_camera_hw(self.cfg, rtsp_url, self.ctx.config.system.mock)
        await self.hw.start()

    async def stop(self) -> None:
        if self.hw is not None:
            await self.hw.stop()
            self.hw = None

    def latest_frame(self) -> tuple[np.ndarray, float] | None:
        """Latest lores RGB frame for vision subscribers (autonomy, future recorders)."""
        if self.hw is None:
            return None
        return self.hw.latest_frame()

    def status(self) -> dict[str, Any]:
        frame = self.latest_frame()
        fresh = frame is not None and (time.monotonic() - frame[1]) < 2.0
        return {
            "resolution": f"{self.cfg.width}x{self.cfg.height}@{self.cfg.fps}",
            "frames_flowing": fresh,
        }
