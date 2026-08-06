"""WiFi hotspot management through NetworkManager (nmcli), with an auto policy.

Policies:
  - always-on:      keep the hotspot up whenever the service runs
  - on-when-no-wifi: bring the hotspot up only when the Pi has no other
                     active WiFi connection (e.g. away from home network)
  - manual:         never touch it automatically (future: REST toggle)
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from typing import Any

from ..core.service import Service

POLL_SECONDS = 10


def _run(cmd: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, check=True, text=True, capture_output=True)
        return True, result.stdout
    except subprocess.CalledProcessError as exc:
        return False, exc.stderr
    except FileNotFoundError as exc:
        return False, str(exc)


class HotspotService(Service):
    name = "hotspot"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cfg = ctx.config.hotspot
        self.available = shutil.which("nmcli") is not None
        self.hotspot_up = False

    async def start(self) -> None:
        if not self.available:
            self.log.warning("nmcli not found; hotspot service inert (dev machine?)")

    async def run(self) -> None:
        if not self.available or self.cfg.policy == "manual":
            await asyncio.Event().wait()
        while True:
            await asyncio.to_thread(self._apply_policy)
            await asyncio.sleep(POLL_SECONDS)

    def _apply_policy(self) -> None:
        want_up = (
            self.cfg.policy == "always-on"
            or (self.cfg.policy == "on-when-no-wifi" and not self._other_wifi_active())
        )
        is_up = self._is_up()
        if want_up and not is_up:
            self.log.info("bringing hotspot '%s' up", self.cfg.ssid)
            self._up()
        elif not want_up and is_up:
            self.log.info("bringing hotspot down (other WiFi active)")
            _run(["nmcli", "connection", "down", self.cfg.connection_name])
        self.hotspot_up = self._is_up()

    def _is_up(self) -> bool:
        ok, out = _run(
            ["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"]
        )
        return ok and any(
            line.startswith(self.cfg.connection_name + ":")
            for line in out.splitlines()
        )

    def _other_wifi_active(self) -> bool:
        ok, out = _run(
            ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"]
        )
        if not ok:
            return False
        for line in out.splitlines():
            parts = line.split(":")
            if (
                len(parts) >= 3
                and parts[1] == "802-11-wireless"
                and parts[0] != self.cfg.connection_name
            ):
                return True
        return False

    def _ensure_profile(self) -> None:
        exists, _ = _run(["nmcli", "connection", "show", self.cfg.connection_name])
        if exists:
            return
        self.log.info("creating hotspot profile '%s'", self.cfg.connection_name)
        _run(
            ["nmcli", "connection", "add", "type", "wifi",
             "ifname", self.cfg.interface, "con-name", self.cfg.connection_name,
             "autoconnect", "no", "ssid", self.cfg.ssid]
        )
        _run(
            ["nmcli", "connection", "modify", self.cfg.connection_name,
             "802-11-wireless.mode", "ap",
             "802-11-wireless.band", self.cfg.band,
             "ipv4.method", "shared",
             "wifi-sec.key-mgmt", "wpa-psk",
             "wifi-sec.psk", self.cfg.password]
        )

    def _up(self) -> None:
        self._ensure_profile()
        ok, err = _run(["nmcli", "connection", "up", self.cfg.connection_name])
        if not ok:
            self.log.error("hotspot up failed: %s", err.strip())

    def ip_address(self) -> str:
        ok, out = _run(
            ["nmcli", "-t", "-f", "IP4.ADDRESS", "device", "show", self.cfg.interface]
        )
        if ok:
            for line in out.splitlines():
                if line.startswith("IP4.ADDRESS"):
                    return line.split(":", 1)[1].split("/")[0]
        return "10.42.0.1"

    def client_count(self) -> int:
        ok, out = _run(["iw", "dev", self.cfg.interface, "station", "dump"])
        return out.count("Station ") if ok else -1

    async def stop(self) -> None:
        if self.available and self.hotspot_up:
            await asyncio.to_thread(
                _run, ["nmcli", "connection", "down", self.cfg.connection_name]
            )
            self.hotspot_up = False

    def status(self) -> dict[str, Any]:
        if not self.available:
            return {"nmcli": False}
        info: dict[str, Any] = {
            "policy": self.cfg.policy,
            "ssid": self.cfg.ssid,
            "up": self.hotspot_up,
        }
        if self.hotspot_up:
            info["ip"] = self.ip_address()
            info["clients"] = self.client_count()
        return info
