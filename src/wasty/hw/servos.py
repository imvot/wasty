"""Drive hardware abstraction: Adafruit ServoKit on the Pi, a logging mock elsewhere."""

from __future__ import annotations

import logging
from typing import Protocol

from ..core.config import DriveConfig

log = logging.getLogger(__name__)


class DriveHW(Protocol):
    def set_steering_angle(self, degrees: float) -> None: ...

    def set_throttle(self, throttle: float) -> None: ...

    def disarm(self) -> None: ...


class ServoKitDrive:
    """Real hardware: steering servo + ESC through the PCA9685 (Adafruit ServoKit)."""

    def __init__(self, cfg: DriveConfig):
        from adafruit_servokit import ServoKit  # only importable on the Pi

        kit = ServoKit(channels=16)
        self._steering = kit.servo[cfg.steering_channel]
        self._motor = kit.continuous_servo[cfg.motor_channel]

    def set_steering_angle(self, degrees: float) -> None:
        self._steering.angle = degrees

    def set_throttle(self, throttle: float) -> None:
        self._motor.throttle = throttle

    def disarm(self) -> None:
        self._motor.throttle = 0.0


class MockDrive:
    """Dev-machine stand-in: remembers and (sparsely) logs commanded values."""

    def __init__(self, cfg: DriveConfig):
        self.steering_angle = cfg.steering_center
        self.throttle = 0.0

    def set_steering_angle(self, degrees: float) -> None:
        if abs(degrees - self.steering_angle) > 0.5:
            log.debug("mock steering -> %.1f deg", degrees)
        self.steering_angle = degrees

    def set_throttle(self, throttle: float) -> None:
        if abs(throttle - self.throttle) > 0.01:
            log.debug("mock throttle -> %.2f", throttle)
        self.throttle = throttle

    def disarm(self) -> None:
        self.throttle = 0.0


def create_drive_hw(cfg: DriveConfig, mock: bool) -> DriveHW:
    return MockDrive(cfg) if mock else ServoKitDrive(cfg)
