"""Camera hardware abstraction.

The real implementation owns the Pi camera via picamera2 and produces:
  - main:  hardware-encoded H.264 pushed to MediaMTX over local RTSP
           (browser pulls WebRTC/WHEP — more compressed, preview only)
  - lores: low-res RGB frames for the vision pipeline
  - optional second H.264 encoder writing high-bitrate MP4 for YOLO training
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path
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

    def start_recording(self, path: Path, bitrate: int) -> None:
        """Start writing main-resolution footage to path (mp4)."""
        ...

    def stop_recording(self) -> Path | None:
        """Stop recording; return the finished file path, or None if idle."""
        ...

    @property
    def recording(self) -> bool: ...


class PiCamera:
    def __init__(self, cfg: CameraConfig, rtsp_url: str):
        self.cfg = cfg
        self.rtsp_url = rtsp_url
        self._picam = None
        self._stream_encoder = None
        self._rec_encoder = None
        self._rec_path: Path | None = None
        self._frame: tuple[np.ndarray, float] | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    async def start(self) -> None:
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
        self._picam.start()

        # Live preview stream — lower bitrate, separate from training recordings.
        self._stream_encoder = H264Encoder(
            bitrate=cfg.bitrate, repeat=True, iperiod=cfg.fps
        )
        rtsp_out = FfmpegOutput(f"-f rtsp -rtsp_transport tcp {self.rtsp_url}")
        self._picam.start_encoder(self._stream_encoder, rtsp_out)

        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_lores, daemon=True)
        self._thread.start()
        log.info(
            "picamera2 %dx%d@%d → RTSP %s",
            cfg.width,
            cfg.height,
            cfg.fps,
            self.rtsp_url,
        )

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

    def start_recording(self, path: Path, bitrate: int) -> None:
        if self._picam is None:
            raise RuntimeError("camera not started")
        if self._rec_encoder is not None:
            raise RuntimeError("already recording")
        from picamera2.encoders import H264Encoder
        from picamera2.outputs import FfmpegOutput

        path.parent.mkdir(parents=True, exist_ok=True)
        # Second encoder on the same main stream — higher bitrate MP4 for training.
        # Independent of the WebRTC/MediaMTX path, so preview compression does not
        # affect saved footage.
        self._rec_path = path
        self._rec_encoder = H264Encoder(
            bitrate=bitrate, repeat=True, iperiod=self.cfg.fps
        )
        self._picam.start_encoder(self._rec_encoder, FfmpegOutput(str(path)))
        log.info(
            "recording %dx%d @ %d bit/s → %s",
            self.cfg.width,
            self.cfg.height,
            bitrate,
            path,
        )

    def stop_recording(self) -> Path | None:
        if self._rec_encoder is None or self._picam is None:
            return None
        path = self._rec_path
        try:
            self._picam.stop_encoder(self._rec_encoder)
        except Exception:
            log.exception("stop recording encoder failed")
        self._rec_encoder = None
        self._rec_path = None
        log.info("recording stopped: %s", path)
        return path

    @property
    def recording(self) -> bool:
        return self._rec_encoder is not None

    async def stop(self) -> None:
        self.stop_recording()
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._picam is not None:
            try:
                if self._stream_encoder is not None:
                    self._picam.stop_encoder(self._stream_encoder)
                self._picam.stop()
                self._picam.close()
            except Exception:
                log.exception("picamera2 shutdown failed")
            self._picam = None
            self._stream_encoder = None

    def latest_frame(self) -> tuple[np.ndarray, float] | None:
        with self._lock:
            return self._frame


class MockCamera:
    """Synthetic camera with optional ffmpeg recording of full-res frames."""

    LORES_FPS = 10

    def __init__(self, cfg: CameraConfig):
        self.cfg = cfg
        self._frame: tuple[np.ndarray, float] | None = None
        self._task: asyncio.Task | None = None
        self._rec_proc: subprocess.Popen | None = None
        self._rec_path: Path | None = None
        self._rec_lock = threading.Lock()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._generate(), name="mock-camera")
        log.info(
            "mock camera %dx%d (lores %dx%d)",
            self.cfg.width,
            self.cfg.height,
            self.cfg.lores_width,
            self.cfg.lores_height,
        )

    def _make_frame(self, w: int, h: int, tick: int) -> np.ndarray:
        gradient = np.linspace(0, 255, w, dtype=np.uint8)
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :, 2] = gradient[np.newaxis, :]
        size = max(20, w // 12)
        x = int((np.sin(tick / 20) * 0.5 + 0.5) * (w - size))
        y = int((np.cos(tick / 31) * 0.5 + 0.5) * (h - size))
        frame[y : y + size, x : x + size] = (0, 220, 90)
        return frame

    async def _generate(self) -> None:
        tick = 0
        while True:
            lores = self._make_frame(self.cfg.lores_width, self.cfg.lores_height, tick)
            self._frame = (lores, time.monotonic())
            with self._rec_lock:
                proc = self._rec_proc
            if proc is not None and proc.stdin is not None:
                try:
                    full = self._make_frame(self.cfg.width, self.cfg.height, tick)
                    proc.stdin.write(full.tobytes())
                except BrokenPipeError:
                    log.warning("recording ffmpeg pipe closed")
                    with self._rec_lock:
                        self._rec_proc = None
            tick += 1
            await asyncio.sleep(1.0 / self.LORES_FPS)

    def start_recording(self, path: Path, bitrate: int) -> None:
        with self._rec_lock:
            if self._rec_proc is not None:
                raise RuntimeError("already recording")
            if shutil.which("ffmpeg") is None:
                raise RuntimeError("ffmpeg not found (required for mock recording)")
            path.parent.mkdir(parents=True, exist_ok=True)
            cmd = [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                f"{self.cfg.width}x{self.cfg.height}",
                "-r",
                str(self.LORES_FPS),
                "-i",
                "-",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-b:v",
                str(bitrate),
                "-pix_fmt",
                "yuv420p",
                str(path),
            ]
            self._rec_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            self._rec_path = path
            log.info("mock recording → %s", path)

    def stop_recording(self) -> Path | None:
        with self._rec_lock:
            proc = self._rec_proc
            path = self._rec_path
            self._rec_proc = None
            self._rec_path = None
        if proc is None:
            return None
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except Exception:
                pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.info("mock recording stopped: %s", path)
        return path

    @property
    def recording(self) -> bool:
        with self._rec_lock:
            return self._rec_proc is not None

    async def stop(self) -> None:
        self.stop_recording()
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
