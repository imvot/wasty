"""AutonomyService: the "click Go and it collects trash" state machine.

    IDLE ──start──> SEARCH ──detection──> APPROACH ──close──> COLLECT
      ^                ^                      │                  │
      │                └──────lost───────────┘                  │
      └──────stop / e-stop (from anywhere)          COLLECT ──done──> SEARCH

It pumps camera frames into the inference worker, reacts to detections, and
expresses movement only as DriveIntent(source=AUTONOMY) — the drive arbiter
guarantees a human can always override or e-stop.
"""

from __future__ import annotations

import asyncio
import time
from enum import StrEnum
from typing import Any

from ...core import bus as topics
from ...core.messages import (
    Detection,
    Detections,
    DriveIntent,
    DriveSource,
    MissionState,
)
from ...core.service import Service
from .worker import InferenceWorker

LOOP_HZ = 10
DETECTION_LOST_SECONDS = 1.5


class State(StrEnum):
    IDLE = "idle"
    SEARCH = "search"
    APPROACH = "approach"
    COLLECT = "collect"


class AutonomyService(Service):
    name = "autonomy"
    depends_on = ("camera", "drive")
    ui_panels = ("autonomy",)

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cfg = ctx.config.autonomy
        self.mission = State.IDLE
        self.worker: InferenceWorker | None = None
        self._command_sub = None
        self._estop_sub = None
        self._last_detection: Detection | None = None
        self._last_detection_ts = 0.0
        self._collect_until = 0.0
        self._last_submit = 0.0

    async def start(self) -> None:
        self.worker = InferenceWorker(self.cfg.detector)
        self.worker.start()
        self._command_sub = self.ctx.bus.subscribe(topics.MISSION_COMMAND)
        self._estop_sub = self.ctx.bus.subscribe(topics.SAFETY_ESTOP)

    async def run(self) -> None:
        period = 1.0 / LOOP_HZ
        while True:
            self._pump_inference()
            self._handle_commands()
            self._step()
            await asyncio.sleep(period)

    # ------------------------------------------------------------- inference

    def _pump_inference(self) -> None:
        now = time.monotonic()
        if now - self._last_submit >= 1.0 / self.cfg.inference_hz:
            camera = self.ctx.registry.get("camera")
            frame = camera.latest_frame() if camera is not None else None
            if frame is not None and self.worker.submit(frame[0], frame[1]):
                self._last_submit = now

        for frame_ts, raw_detections in self.worker.poll_results():
            items = [Detection.model_validate(d) for d in raw_detections]
            self.ctx.bus.publish(
                topics.VISION_DETECTIONS,
                Detections(items=items, frame_ts=frame_ts),
            )
            if items:
                best = max(items, key=lambda d: d.confidence)
                self._last_detection = best
                self._last_detection_ts = time.monotonic()

    # -------------------------------------------------------------- commands

    def _handle_commands(self) -> None:
        estop = self._estop_sub.latest()
        if estop is not None and estop.engaged and self.mission != State.IDLE:
            self._transition(State.IDLE, "e-stop")
            return
        for cmd in self._command_sub.drain():
            if cmd.action == "start" and self.mission == State.IDLE:
                self._transition(State.SEARCH, "mission started")
            elif cmd.action == "stop" and self.mission != State.IDLE:
                self._transition(State.IDLE, "mission stopped")

    # --------------------------------------------------------- state machine

    def _transition(self, new_state: State, reason: str) -> None:
        self.log.info("%s -> %s (%s)", self.mission.value, new_state.value, reason)
        self.mission = new_state
        if new_state == State.COLLECT:
            self._collect_until = time.monotonic() + self.cfg.collect_seconds
        self.ctx.bus.publish(
            topics.MISSION_STATE, MissionState(state=new_state.value, detail=reason)
        )

    def _detection_fresh(self) -> bool:
        return (
            self._last_detection is not None
            and time.monotonic() - self._last_detection_ts < DETECTION_LOST_SECONDS
        )

    def _step(self) -> None:
        if self.mission == State.IDLE:
            return

        if self.mission == State.SEARCH:
            if self._detection_fresh():
                self._transition(State.APPROACH, "target acquired")
            else:
                self._intent(self.cfg.search_throttle, self.cfg.search_steering)

        elif self.mission == State.APPROACH:
            if not self._detection_fresh():
                self._transition(State.SEARCH, "target lost")
            else:
                det = self._last_detection
                if det.w * det.h >= self.cfg.approach_area:
                    self._transition(State.COLLECT, "target reached")
                else:
                    # steer proportionally toward the target's horizontal offset
                    steering = max(-1.0, min(1.0, (det.cx - 0.5) * 2.0))
                    self._intent(self.cfg.approach_throttle, steering)

        elif self.mission == State.COLLECT:
            if time.monotonic() >= self._collect_until:
                self._last_detection = None
                self._transition(State.SEARCH, "collected, resuming search")
            else:
                self._intent(self.cfg.approach_throttle, 0.0)

    def _intent(self, throttle: float, steering: float) -> None:
        self.ctx.bus.publish(
            topics.DRIVE_INTENT,
            DriveIntent(
                source=DriveSource.AUTONOMY, throttle=throttle, steering=steering
            ),
        )

    # ------------------------------------------------------------- lifecycle

    async def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.worker = None
        for sub in (self._command_sub, self._estop_sub):
            if sub is not None:
                sub.close()
        self._command_sub = self._estop_sub = None
        self.mission = State.IDLE

    def status(self) -> dict[str, Any]:
        return {
            "mission": self.mission.value,
            "detector": self.cfg.detector,
            "worker_alive": self.worker.alive if self.worker else False,
        }
