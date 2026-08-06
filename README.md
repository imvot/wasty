# Wasty

A Raspberry Pi RC car that collects trash. One systemd service runs a modular
stack: WiFi hotspot, low-latency WebRTC camera livefeed, browser drive
controls, and an autonomy state machine ("click GO and it collects trash").

## Architecture

A single asyncio process hosts independent, restartable services coordinated
by an in-process event bus. MediaMTX runs as a supervised child process;
CPU-heavy vision inference runs in a worker subprocess.

```
browser (React SPA)
   │  WebRTC/WHEP video          ┌───────────────────────────────┐
   │◄────────────── MediaMTX ◄───┤ CameraService (picamera2)     │
   │  WebSocket {drive,estop,go} │        │ lores frames         │
   ▼                             │        ▼                      │
WebService ──DriveIntent──►      │  inference worker (detector)  │
                          ▼      │        │ detections           │
AutonomyService ──DriveIntent──► │        ▼                      │
                          ▼      │  AutonomyService (mission)    │
                   DriveService ─┤  HotspotService (nmcli)       │
                   (arbiter,     │  MediamtxService (supervisor) │
                    ServoKit)    └───────────────────────────────┘
```

Key contracts:

- **Services** (`src/wasty/core/service.py`): `start/run/stop`, declared
  dependencies, health state. The registry boots them in dependency order and
  restarts crashed ones with backoff.
- **Bus topics** (`src/wasty/core/bus.py`): `drive.intent`, `drive.state`,
  `safety.estop`, `vision.detections`, `mission.command`, `mission.state`.
  Typed pydantic messages (`src/wasty/core/messages.py`).
- **Drive arbitration** (`src/wasty/services/drive.py`): e-stop > fresh manual
  > fresh autonomy > neutral. Manual commands need a >=5 Hz heartbeat
  (deadman); e-stop cuts throttle instantly; only this service touches
  ServoKit.
- **Capabilities** (`/api/capabilities`): running services advertise UI
  panels; the React app renders whatever the robot supports. Adding a page
  element = new panel component + a service advertising it.
- **Detector** (`src/wasty/services/autonomy/detector.py`): swap the stub for
  a real model (ONNX/NCNN on the Pi 5 CPU) without touching anything else.

## Install on the Pi

```bash
git clone <this repo> && cd wasty
# build the UI first (on any machine with node, copy dist/ over, or build on the Pi)
cd webui && npm install && npm run build && cd ..
sudo scripts/install.sh
sudo systemctl start wasty
```

Per-robot settings (hotspot SSID/password, servo channels/trim, camera
resolution) go in `config/local.yaml`, which overlays `config/default.yaml`
and is gitignored:

```yaml
hotspot:
  ssid: Wasty
  password: pick-something-strong
drive:
  steering_center: 105.0
```

Connect to the hotspot, open `http://10.42.0.1:8080/`.

## Develop on a laptop (no robot needed)

```bash
python3 -m venv .venv-dev && .venv-dev/bin/pip install -e .
.venv-dev/bin/wasty --mock          # mock servos + synthetic camera
```

- Web UI dev server with hot reload: `cd webui && npm run dev`
  (proxies `/api` and `/ws` to `http://127.0.0.1:8080`, override with
  `WASTY_BACKEND`).
- Set `autonomy.detector: mock-blob` in a config overlay to make the mission
  state machine chase the synthetic green square end to end.
- `wastyctl status | estop on|off | mission start|stop` talks to the running
  service.

## Layout

```
config/            default.yaml + local.yaml overlay
systemd/           wasty.service unit
scripts/           install.sh
src/wasty/
  core/            config, event bus, service base, registry
  hw/              servo + camera drivers (real and mock)
  services/        hotspot, mediamtx, camera, web, drive, autonomy/
webui/             React + Vite SPA (panels in src/panels/)
legacy/            the original single-script codebase, kept for reference
```
