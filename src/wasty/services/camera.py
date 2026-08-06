"""CameraService: owns the camera, feeds MediaMTX (RTSP), vision tap, and recordings."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..core import bus as topics
from ..core.config import resolve_recording_dir
from ..core.messages import RecordingState
from ..core.service import Service
from ..hw.camera import create_camera_hw


class CameraService(Service):
    name = "camera"
    depends_on = ("mediamtx",)
    ui_panels = ("video",)

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cfg = ctx.config.camera
        self.rec_cfg = ctx.config.recording
        self.hw = None
        self._recording = False
        self._rec_filename: str | None = None
        self._rec_started_at: str | None = None
        self._rec_path: Path | None = None
        self._rec_error: str | None = None

        if self.rec_cfg.enabled:
            # Advertise so the Livefeed page shows the Record control.
            self.ui_panels = ("video", "recording")

    async def start(self) -> None:
        mtx_cfg = self.ctx.config.mediamtx
        rtsp_url = f"rtsp://127.0.0.1:{mtx_cfg.rtsp_port}/{mtx_cfg.stream_name}"
        self.hw = create_camera_hw(self.cfg, rtsp_url, self.ctx.config.system.mock)
        await self.hw.start()
        if self.rec_cfg.enabled:
            dest = resolve_recording_dir(self.rec_cfg.directory)
            self.log.info("recordings directory: %s", dest)

    async def stop(self) -> None:
        if self._recording:
            await self.stop_recording()
        if self.hw is not None:
            await self.hw.stop()
            self.hw = None

    def latest_frame(self) -> tuple[np.ndarray, float] | None:
        if self.hw is None:
            return None
        return self.hw.latest_frame()

    def _publish(self, error: str | None = None) -> RecordingState:
        state = RecordingState(
            recording=self._recording,
            filename=self._rec_filename,
            started_at=self._rec_started_at,
            path=str(self._rec_path) if self._rec_path else None,
            error=error if error is not None else self._rec_error,
        )
        self.ctx.bus.publish(topics.RECORDING_STATE, state)
        return state

    async def start_recording(self) -> RecordingState:
        if not self.rec_cfg.enabled:
            return self._publish(error="recording disabled in config")
        if self.hw is None:
            return self._publish(error="camera not ready")
        if self._recording:
            return self._publish()

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{stamp}.mp4"
        dest_dir = resolve_recording_dir(self.rec_cfg.directory)
        path = dest_dir / filename
        try:
            await asyncio.to_thread(
                self.hw.start_recording, path, self.rec_cfg.bitrate
            )
        except Exception as exc:
            self.log.exception("start recording failed")
            self._rec_error = str(exc)
            return self._publish(error=str(exc))

        self._recording = True
        self._rec_filename = filename
        self._rec_started_at = datetime.now().isoformat(timespec="seconds")
        self._rec_path = path
        self._rec_error = None
        self.log.info("recording started: %s", path)
        return self._publish()

    async def stop_recording(self) -> RecordingState:
        if not self._recording or self.hw is None:
            self._recording = False
            return self._publish()
        try:
            path = await asyncio.to_thread(self.hw.stop_recording)
        except Exception as exc:
            self.log.exception("stop recording failed")
            self._recording = False
            self._rec_error = str(exc)
            return self._publish(error=str(exc))

        self._recording = False
        if path is not None:
            self._rec_path = path
            self._rec_filename = path.name
        self.log.info("recording saved: %s", self._rec_path)
        return self._publish()

    def status(self) -> dict[str, Any]:
        frame = self.latest_frame()
        fresh = frame is not None and (time.monotonic() - frame[1]) < 2.0
        info: dict[str, Any] = {
            "resolution": f"{self.cfg.width}x{self.cfg.height}@{self.cfg.fps}",
            "frames_flowing": fresh,
            "recording": self._recording,
        }
        if self.rec_cfg.enabled:
            info["recordings_dir"] = str(
                resolve_recording_dir(self.rec_cfg.directory)
            )
            info["recording_bitrate"] = self.rec_cfg.bitrate
        if self._rec_filename:
            info["last_file"] = self._rec_filename
        if self._rec_error:
            info["recording_error"] = self._rec_error
        return info
