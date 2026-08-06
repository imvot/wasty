"""Camera hardware abstraction.

The real implementation owns the Pi camera via picamera2 and produces two
streams:
  - main:  hardware-encoded H.264 pushed to MediaMTX over local RTSP
           (the browser then pulls it as WebRTC/WHEP from MediaMTX)
  - lores: low-res RGB frames kept in memory for the vision pipeline

The mock generates a synthetic moving test pattern so the whole stack
(vision included) runs on a dev machine.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Protocol

import numpy as np

from ..core.config import CameraConfig

log = logging.getLogger(__name__)


class CameraHW(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def latest_frame(self) -> tuple[np.ndarray, float] | None:
        """Latest lores RGB frame and its monotonic timestamp, or None."""
        ...


class PiCamera:
    def __init__(self, cfg: CameraConfig, rtsp_url: str):
        self.cfg = cfg
        self.rtsp_url = rtsp_url
        self._picam = None
        self._frame: tuple[np.ndarray, float] | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    async def start(self) -> None:
        # Imports deferred: picamera2 exists only on the Pi (apt package).
        from picamera2 import Picamera2
        from picamera2.encoders import H264Encoder
        from picamera2.outputs import FfmpegOutput

        cfg = self.cfg
        self._picam = Picamera2()
        video_config = self._picam.create_video_configuration(
            main={"size": (cfg.width, cfg.height), "format": "YUV420"},
            lores={"size": (cfg.lores_width, cfg.lores_height), "format": "RGB888"},
            controls={"FrameRate": cfg.fps},
        )
        self._picam.configure(video_config)
        encoder = H264Encoder(bitrate=cfg.bitrate, repeat=True, iperiod=cfg.fps)
        output = FfmpegOutput(f"-f rtsp -rtsp_transport tcp {self.rtsp_url}")
        self._picam.start_recording(encoder, output)

        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_lores, daemon=True)
        self._thread.start()
        log.info("picamera2 streaming H.264 to %s", self.rtsp_url)

    def _poll_lores(self) -> None:
        interval = 1.0 / self.cfg.fps
        while not self._stop.is_set():
            try:
                frame = self._picam.capture_array("lores")
            except Exception:
                log.exception("lores capture failed")
                time.sleep(1.0)
                continue
            with self._lock:
                self._frame = (frame, time.monotonic())
            time.sleep(interval)

    async def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._picam is not None:
            try:
                self._picam.stop_recording()
                self._picam.close()
            except Exception:
                log.exception("picamera2 shutdown failed")
            self._picam = None

    def latest_frame(self) -> tuple[np.ndarray, float] | None:
        with self._lock:
            return self._frame


class MockCamera:
    """Synthetic moving test pattern; no RTSP publishing."""

    FPS = 10

    def __init__(self, cfg: CameraConfig):
        self.cfg = cfg
        self._frame: tuple[np.ndarray, float] | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._generate(), name="mock-camera")
        log.info("mock camera generating %dx%d test frames",
                 self.cfg.lores_width, self.cfg.lores_height)

    async def _generate(self) -> None:
        w, h = self.cfg.lores_width, self.cfg.lores_height
        gradient = np.linspace(0, 255, w, dtype=np.uint8)
        base = np.zeros((h, w, 3), dtype=np.uint8)
        base[:, :, 2] = gradient[np.newaxis, :]
        tick = 0
        while True:
            frame = base.copy()
            # moving bright square, handy as a fake "detectable object"
            size = 30
            x = int((np.sin(tick / 20) * 0.5 + 0.5) * (w - size))
            y = int((np.cos(tick / 31) * 0.5 + 0.5) * (h - size))
            frame[y : y + size, x : x + size] = (0, 220, 90)
            self._frame = (frame, time.monotonic())
            tick += 1
            await asyncio.sleep(1.0 / self.FPS)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def latest_frame(self) -> tuple[np.ndarray, float] | None:
        return self._frame


def create_camera_hw(cfg: CameraConfig, rtsp_url: str, mock: bool) -> CameraHW:
    return MockCamera(cfg) if mock else PiCamera(cfg, rtsp_url)
