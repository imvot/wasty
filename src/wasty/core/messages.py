"""Typed messages exchanged on the event bus."""

from __future__ import annotations

import time
from enum import StrEnum

from pydantic import BaseModel, Field


def now() -> float:
    return time.monotonic()


class DriveSource(StrEnum):
    MANUAL = "manual"
    AUTONOMY = "autonomy"


class DriveIntent(BaseModel):
    """A request to move: throttle and steering normalized to [-1, 1].

    steering: -1 = full left, +1 = full right.
    """

    source: DriveSource
    throttle: float = 0.0
    steering: float = 0.0
    ts: float = Field(default_factory=now)


class DriveState(BaseModel):
    throttle: float
    steering: float
    steering_angle: float
    active_source: str  # "manual" | "autonomy" | "none" | "estop"
    estop: bool
    ts: float = Field(default_factory=now)


class EStop(BaseModel):
    engaged: bool
    ts: float = Field(default_factory=now)


class Detection(BaseModel):
    label: str
    confidence: float
    # Normalized bbox center + size, all in [0, 1].
    cx: float
    cy: float
    w: float
    h: float


class Detections(BaseModel):
    items: list[Detection] = []
    frame_ts: float = 0.0
    ts: float = Field(default_factory=now)


class MissionCommand(BaseModel):
    action: str  # "start" | "stop"
    ts: float = Field(default_factory=now)


class MissionState(BaseModel):
    state: str  # "idle" | "search" | "approach" | "collect"
    detail: str = ""
    ts: float = Field(default_factory=now)
