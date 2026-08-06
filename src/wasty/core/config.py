"""Typed configuration loaded from YAML (default.yaml + optional local.yaml)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO_ROOT / "config" / "default.yaml"
LOCAL_CONFIG = REPO_ROOT / "config" / "local.yaml"


class SystemConfig(BaseModel):
    mock: bool = False
    log_level: str = "INFO"


class HotspotConfig(BaseModel):
    enabled: bool = True
    policy: Literal["always-on", "on-when-no-wifi", "manual"] = "always-on"
    ssid: str = "Wasty"
    password: str = "change-me-1234"
    interface: str = "wlan1"
    band: Literal["a", "bg"] = "a"
    connection_name: str = "wasty-hotspot"


class MediamtxConfig(BaseModel):
    enabled: bool = True
    binary: str = "/usr/local/bin/mediamtx"
    rtsp_port: int = 8554
    webrtc_port: int = 8889
    stream_name: str = "cam"


class CameraConfig(BaseModel):
    enabled: bool = True
    width: int = 854
    height: int = 480
    fps: int = 30
    bitrate: int = 1_000_000
    lores_width: int = 320
    lores_height: int = 240


class WebConfig(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080


class DriveConfig(BaseModel):
    enabled: bool = True
    steering_channel: int = 0
    motor_channel: int = 1
    steering_center: float = 105.0
    steering_left: float = 145.0
    steering_right: float = 70.0
    max_throttle: float = 0.6
    throttle_ramp: float = 2.0
    manual_timeout: float = 0.5
    autonomy_timeout: float = 1.0
    arm_seconds: float = 2.0
    loop_hz: int = 50


class AutonomyConfig(BaseModel):
    enabled: bool = True
    detector: str = "stub"
    inference_hz: float = 5.0
    search_throttle: float = 0.12
    search_steering: float = -0.7
    approach_throttle: float = 0.2
    approach_area: float = 0.25
    collect_seconds: float = 2.0


class Config(BaseModel):
    system: SystemConfig = SystemConfig()
    hotspot: HotspotConfig = HotspotConfig()
    mediamtx: MediamtxConfig = MediamtxConfig()
    camera: CameraConfig = CameraConfig()
    web: WebConfig = WebConfig()
    drive: DriveConfig = DriveConfig()
    autonomy: AutonomyConfig = AutonomyConfig()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path | None = None, *, mock: bool | None = None) -> Config:
    """Load default.yaml, overlay local.yaml (or an explicit path), apply CLI overrides."""
    data: dict[str, Any] = {}
    if DEFAULT_CONFIG.exists():
        data = yaml.safe_load(DEFAULT_CONFIG.read_text()) or {}
    overlay_path = path if path is not None else LOCAL_CONFIG
    if overlay_path and overlay_path.exists():
        overlay = yaml.safe_load(overlay_path.read_text()) or {}
        data = _deep_merge(data, overlay)
    config = Config.model_validate(data)
    if mock is not None:
        config.system.mock = mock
    return config
