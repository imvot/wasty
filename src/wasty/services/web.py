"""WebService: FastAPI app serving the SPA, REST status/capabilities, and the
WebSocket control/telemetry channel.

WebSocket protocol — JSON envelopes {"type": ..., "payload": ...}:

  client -> server:
    drive    {throttle: float, steering: float}     (send >= 5 Hz while driving)
    estop    {engaged: bool}
    mission  {action: "start" | "stop"}

  server -> client:
    drive.state    DriveState
    mission.state  MissionState
    detections     Detections
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..core import bus as topics
from ..core.messages import DriveIntent, DriveSource, EStop, MissionCommand
from ..core.service import Service

REPO_ROOT = Path(__file__).resolve().parents[3]
WEBUI_DIST = REPO_ROOT / "webui" / "dist"

PLACEHOLDER_HTML = """<!doctype html>
<html><body style="background:#111;color:#eee;font-family:sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh">
<div><h2>Wasty is running</h2>
<p>The web UI has not been built yet. Run:</p>
<pre>cd webui && npm install && npm run build</pre></div>
</body></html>"""


class WebService(Service):
    name = "web"
    ui_panels = ("status",)

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cfg = ctx.config.web
        self._server: uvicorn.Server | None = None
        self._clients: set[WebSocket] = set()
        self._broadcast_task: asyncio.Task | None = None

    # ------------------------------------------------------------------ app

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="wasty")

        @app.get("/api/status")
        async def api_status() -> dict[str, Any]:
            return {"services": self.ctx.registry.status()}

        @app.get("/api/capabilities")
        async def api_capabilities() -> dict[str, Any]:
            mtx = self.ctx.config.mediamtx
            return {
                "panels": self.ctx.registry.ui_panels(),
                "stream": {
                    "name": mtx.stream_name,
                    "webrtc_port": mtx.webrtc_port,
                },
            }

        @app.post("/api/estop")
        async def api_estop(payload: dict[str, Any]) -> dict[str, Any]:
            engaged = bool(payload.get("engaged", True))
            self.ctx.bus.publish(topics.SAFETY_ESTOP, EStop(engaged=engaged))
            return {"ok": True, "engaged": engaged}

        @app.post("/api/mission")
        async def api_mission(payload: dict[str, Any]) -> dict[str, Any]:
            action = str(payload.get("action", "stop"))
            self.ctx.bus.publish(topics.MISSION_COMMAND, MissionCommand(action=action))
            return {"ok": True, "action": action}

        @app.websocket("/ws")
        async def ws_endpoint(ws: WebSocket) -> None:
            await ws.accept()
            self._clients.add(ws)
            try:
                while True:
                    raw = await ws.receive_text()
                    self._handle_client_message(raw)
            except WebSocketDisconnect:
                pass
            finally:
                self._clients.discard(ws)

        if WEBUI_DIST.exists():
            app.mount(
                "/", StaticFiles(directory=WEBUI_DIST, html=True), name="webui"
            )
        else:

            @app.get("/")
            async def placeholder() -> HTMLResponse:
                return HTMLResponse(PLACEHOLDER_HTML)

        return app

    # ----------------------------------------------------------- ws handling

    def _handle_client_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
            kind = msg.get("type")
            payload = msg.get("payload") or {}
        except (json.JSONDecodeError, AttributeError):
            self.log.warning("bad ws message: %.100s", raw)
            return

        if kind == "drive":
            self.ctx.bus.publish(
                topics.DRIVE_INTENT,
                DriveIntent(
                    source=DriveSource.MANUAL,
                    throttle=float(payload.get("throttle", 0.0)),
                    steering=float(payload.get("steering", 0.0)),
                ),
            )
        elif kind == "estop":
            self.ctx.bus.publish(
                topics.SAFETY_ESTOP, EStop(engaged=bool(payload.get("engaged", True)))
            )
        elif kind == "mission":
            self.ctx.bus.publish(
                topics.MISSION_COMMAND,
                MissionCommand(action=str(payload.get("action", "stop"))),
            )
        else:
            self.log.debug("unknown ws message type: %s", kind)

    async def _broadcast_loop(self) -> None:
        """Forward bus telemetry to every connected WebSocket client."""
        subs = {
            "drive.state": self.ctx.bus.subscribe(topics.DRIVE_STATE),
            "mission.state": self.ctx.bus.subscribe(topics.MISSION_STATE),
            "detections": self.ctx.bus.subscribe(topics.VISION_DETECTIONS),
        }

        async def pump(kind: str, sub) -> None:
            async for message in sub:
                if not self._clients:
                    continue
                text = json.dumps({"type": kind, "payload": message.model_dump()})
                dead = []
                for ws in self._clients:
                    try:
                        await ws.send_text(text)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    self._clients.discard(ws)

        await asyncio.gather(*(pump(kind, sub) for kind, sub in subs.items()))

    # ------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        config = uvicorn.Config(
            self._build_app(),
            host=self.cfg.host,
            port=self.cfg.port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._broadcast_task = asyncio.create_task(
            self._broadcast_loop(), name="web-broadcast"
        )

    async def run(self) -> None:
        self.log.info("web UI on http://%s:%d/", self.cfg.host, self.cfg.port)
        await self._server.serve()

    async def stop(self) -> None:
        if self._broadcast_task is not None:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
            self._broadcast_task = None
        if self._server is not None:
            self._server.should_exit = True
            self._server = None

    def status(self) -> dict[str, Any]:
        return {
            "port": self.cfg.port,
            "clients": len(self._clients),
            "spa_built": WEBUI_DIST.exists(),
        }
