"""DriveService: the single authority over motion.

Everyone (manual WebSocket control, autonomy) publishes DriveIntent messages
on the bus. This service arbitrates by priority and freshness:

    e-stop  >  manual (fresh)  >  autonomy (fresh)  >  neutral

Fresh means "received within the source's timeout" — a lost WiFi link or a
crashed autonomy loop automatically decays to neutral (deadman). Throttle
changes are ramped; this service is the only code that touches ServoKit.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from ..core import bus as topics
from ..core.messages import DriveIntent, DriveSource, DriveState
from ..core.service import Service
from ..hw.servos import create_drive_hw

STATE_PUBLISH_HZ = 10


class DriveService(Service):
    name = "drive"
    ui_panels = ("drive", "estop")

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cfg = ctx.config.drive
        self.hw = None
        self._intent_sub = None
        self._estop_sub = None
        self._latest: dict[DriveSource, DriveIntent] = {}
        self.estop = False
        self._throttle = 0.0  # current (ramped) output throttle
        self._steering = 0.0
        self._active_source = "none"

    async def start(self) -> None:
        self.hw = create_drive_hw(self.cfg, self.ctx.config.system.mock)
        self._intent_sub = self.ctx.bus.subscribe(topics.DRIVE_INTENT, maxsize=64)
        self._estop_sub = self.ctx.bus.subscribe(topics.SAFETY_ESTOP)

        self.log.info("arming ESC (neutral for %.1fs)", self.cfg.arm_seconds)
        self.hw.set_throttle(0.0)
        self.hw.set_steering_angle(self.cfg.steering_center)
        await asyncio.sleep(self.cfg.arm_seconds)
        self.log.info("armed")

    async def run(self) -> None:
        period = 1.0 / self.cfg.loop_hz
        publish_every = max(1, self.cfg.loop_hz // STATE_PUBLISH_HZ)
        tick = 0
        while True:
            self._ingest_messages()
            target_throttle, steering, source = self._arbitrate()
            self._apply(target_throttle, steering, period)
            self._active_source = source
            if tick % publish_every == 0:
                self._publish_state()
            tick += 1
            await asyncio.sleep(period)

    def _ingest_messages(self) -> None:
        for intent in self._intent_sub.drain():
            self._latest[intent.source] = intent
        estop_msg = self._estop_sub.latest()
        if estop_msg is not None and estop_msg.engaged != self.estop:
            self.estop = estop_msg.engaged
            if self.estop:
                self._latest.clear()  # forget stale intents while stopped
            self.log.warning("E-STOP %s", "ENGAGED" if self.estop else "released")

    def _arbitrate(self) -> tuple[float, float, str]:
        if self.estop:
            return 0.0, 0.0, "estop"
        now = time.monotonic()
        manual = self._latest.get(DriveSource.MANUAL)
        if manual is not None and now - manual.ts < self.cfg.manual_timeout:
            return manual.throttle, manual.steering, "manual"
        autonomy = self._latest.get(DriveSource.AUTONOMY)
        if autonomy is not None and now - autonomy.ts < self.cfg.autonomy_timeout:
            return autonomy.throttle, autonomy.steering, "autonomy"
        return 0.0, 0.0, "none"

    def _apply(self, target_throttle: float, steering: float, period: float) -> None:
        if self.estop:
            self._throttle = 0.0  # e-stop cuts instantly, no ramp
        else:
            limit = self.cfg.max_throttle
            target = max(-limit, min(limit, target_throttle))
            max_step = self.cfg.throttle_ramp * period
            delta = target - self._throttle
            if abs(delta) > max_step:
                delta = max_step if delta > 0 else -max_step
            self._throttle += delta

        self._steering = max(-1.0, min(1.0, steering))
        self.hw.set_throttle(self._throttle)
        self.hw.set_steering_angle(self._steering_to_angle(self._steering))

    def _steering_to_angle(self, steer: float) -> float:
        """Map normalized steer [-1 left, +1 right] to servo degrees."""
        center = self.cfg.steering_center
        if steer < 0:
            return center + (-steer) * (self.cfg.steering_left - center)
        return center + steer * (self.cfg.steering_right - center)

    def _publish_state(self) -> None:
        self.ctx.bus.publish(
            topics.DRIVE_STATE,
            DriveState(
                throttle=round(self._throttle, 3),
                steering=round(self._steering, 3),
                steering_angle=round(self._steering_to_angle(self._steering), 1),
                active_source=self._active_source,
                estop=self.estop,
            ),
        )

    async def stop(self) -> None:
        if self.hw is not None:
            self.hw.set_steering_angle(self.cfg.steering_center)
            self.hw.disarm()
        if self._intent_sub is not None:
            self._intent_sub.close()
            self._intent_sub = None
        if self._estop_sub is not None:
            self._estop_sub.close()
            self._estop_sub = None

    def status(self) -> dict[str, Any]:
        return {
            "estop": self.estop,
            "throttle": round(self._throttle, 3),
            "steering": round(self._steering, 3),
            "active_source": self._active_source,
        }
