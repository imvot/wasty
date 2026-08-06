#!/usr/bin/env python3
"""
livefeed.py — WiFi hotspot + low-latency Pi Camera WebRTC stream, controllable
as a background service.

Usage:
    sudo python3 livefeed.py start      # bring up hotspot, start camera stream + webpage
    sudo python3 livefeed.py stop       # tear everything down
    sudo python3 livefeed.py restart
    sudo python3 livefeed.py status     # show hotspot / stream / webpage status

How it works:
    - Hotspot is created/managed via NetworkManager (nmcli), same approach as
      the manual `nmcli device wifi hotspot` command.
    - Camera capture + H.264 encode + WebRTC serving is handled by MediaMTX
      (https://github.com/bluenviron/mediamtx), which has native Raspberry Pi
      Camera support (the `rpiCamera` source) — no ffmpeg glue needed, and it
      uses the Pi's hardware encoder. This script just writes MediaMTX's
      config and supervises the process; no Python WebRTC library required.
    - A tiny custom webpage (plain http.server, no framework) hosts a WHEP
      (WebRTC-HTTP Egress Protocol) player that connects to MediaMTX.
    - `start` launches a detached supervisor subprocess that owns the
      hotspot + MediaMTX + webserver and lives until `stop` sends it SIGTERM.

Requirements:
    - Raspberry Pi OS Bookworm (NetworkManager) with a Pi Camera attached
    - MediaMTX binary for arm64, downloaded from:
          https://github.com/bluenviron/mediamtx/releases
      Extract it and place the binary at /usr/local/bin/mediamtx (or edit
      MEDIAMTX_BIN below / put it on your PATH).
    - Run with sudo — NetworkManager hotspot changes need root.
"""

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# ----------------------------------------------------------------------------
# Configuration — edit these to taste
# ----------------------------------------------------------------------------

SSID = "PiCam"
PASSWORD = "raspberry1234"          # CHANGE THIS. 8+ chars, WPA2.
WLAN_IFACE = "wlan1"
HOTSPOT_CONN_NAME = "Hotspot"
HOTSPOT_BAND = "a"                 # "a" = 5GHz (faster, less congested), "bg" = 2.4GHz

STREAM_NAME = "cam"
CAMERA_WIDTH = 854
CAMERA_HEIGHT = 480
CAMERA_FPS = 30
CAMERA_BITRATE = 1_000_000         # bits/sec, H.264

MEDIAMTX_BIN = shutil.which("mediamtx") or "/usr/local/bin/mediamtx"
WEBRTC_PORT = 8889                 # MediaMTX's own WebRTC/WHEP port
PAGE_PORT = 8080                   # our custom webpage

BASE_DIR = Path.home() / ".livefeed"
PID_FILE = BASE_DIR / "supervisor.pid"
MEDIAMTX_CONFIG = BASE_DIR / "mediamtx.yml"
MEDIAMTX_LOG = BASE_DIR / "mediamtx.log"
SUPERVISOR_LOG = BASE_DIR / "supervisor.log"
WEB_DIR = BASE_DIR / "web"

# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def log(msg: str, f=None):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if f:
        f.write(line + "\n")
        f.flush()


def run(cmd, **kwargs):
    """Run a command, raise on failure."""
    return subprocess.run(cmd, check=True, text=True,
                           capture_output=True, **kwargs)


def try_run(cmd):
    """Run a command, swallow failure, return (ok, output)."""
    try:
        r = run(cmd)
        return True, r.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr
    except FileNotFoundError as e:
        return False, str(e)


def port_open(host, port, timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def read_pidfile():
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
    except ValueError:
        return None
    return pid if pid_alive(pid) else None


# ----------------------------------------------------------------------------
# Hotspot (NetworkManager / nmcli)
# ----------------------------------------------------------------------------

def hotspot_is_up() -> bool:
    ok, out = try_run(["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"])
    return ok and any(line.startswith(HOTSPOT_CONN_NAME + ":") for line in out.splitlines())


def hotspot_up(f=None):
    if hotspot_is_up():
        log("Hotspot already active", f)
        return
    exists, _ = try_run(["nmcli", "connection", "show", HOTSPOT_CONN_NAME])
    if not exists:
        log(f"Creating hotspot profile '{HOTSPOT_CONN_NAME}'", f)
        run(["nmcli", "connection", "add", "type", "wifi",
             "ifname", WLAN_IFACE, "con-name", HOTSPOT_CONN_NAME,
             "autoconnect", "no", "ssid", SSID])
        run(["nmcli", "connection", "modify", HOTSPOT_CONN_NAME,
             "802-11-wireless.mode", "ap",
             "802-11-wireless.band", HOTSPOT_BAND])
        run(["nmcli", "connection", "modify", HOTSPOT_CONN_NAME,
             "ipv4.method", "shared"])
        run(["nmcli", "connection", "modify", HOTSPOT_CONN_NAME,
             "wifi-sec.key-mgmt", "wpa-psk",
             "wifi-sec.psk", PASSWORD])
    log(f"Bringing up hotspot '{SSID}'", f)
    run(["nmcli", "connection", "up", HOTSPOT_CONN_NAME])


def hotspot_down(f=None):
    if hotspot_is_up():
        log("Bringing down hotspot", f)
        try_run(["nmcli", "connection", "down", HOTSPOT_CONN_NAME])


def hotspot_ip() -> str:
    ok, out = try_run(["nmcli", "-t", "-f", "IP4.ADDRESS", "device", "show", WLAN_IFACE])
    if ok:
        for line in out.splitlines():
            if line.startswith("IP4.ADDRESS"):
                return line.split(":", 1)[1].split("/")[0]
    return "10.42.0.1"  # NetworkManager's default shared-mode gateway address


def connected_client_count() -> int:
    ok, out = try_run(["iw", "dev", WLAN_IFACE, "station", "dump"])
    if not ok:
        return -1
    return out.count("Station ")


# ----------------------------------------------------------------------------
# MediaMTX — camera capture + H.264 encode + WebRTC/WHEP serving
# ----------------------------------------------------------------------------

def write_mediamtx_config():
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    config = textwrap.dedent(f"""\
        # Auto-generated by livefeed.py — do not edit by hand
        logLevel: info
        webrtc: yes
        webrtcAddress: :{WEBRTC_PORT}

        paths:
          {STREAM_NAME}:
            source: rpiCamera
            rpiCameraWidth: {CAMERA_WIDTH}
            rpiCameraHeight: {CAMERA_HEIGHT}
            rpiCameraFPS: {CAMERA_FPS}
            rpiCameraBitrate: {CAMERA_BITRATE}
            rpiCameraIDRPeriod: 30
    """)
    MEDIAMTX_CONFIG.write_text(config)


def mediamtx_available() -> bool:
    return Path(MEDIAMTX_BIN).exists() or shutil.which("mediamtx") is not None


def start_mediamtx(f=None) -> subprocess.Popen:
    write_mediamtx_config()
    log_fh = open(MEDIAMTX_LOG, "a")
    log(f"Starting MediaMTX ({MEDIAMTX_BIN})", f)
    return subprocess.Popen([MEDIAMTX_BIN, str(MEDIAMTX_CONFIG)],
                             stdout=log_fh, stderr=log_fh)


# ----------------------------------------------------------------------------
# Custom low-latency webpage (WHEP/WebRTC player, no dependencies)
# ----------------------------------------------------------------------------

def write_webpage():
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    html = textwrap.dedent(f"""\
        <!doctype html>
        <html>
        <head>
          <meta charset="utf-8">
          <title>Pi Camera — Live</title>
          <style>
            body {{ margin:0; background:#111; display:flex; flex-direction:column;
                    align-items:center; justify-content:center; height:100vh;
                    font-family:sans-serif; color:#eee; }}
            video {{ max-width:100vw; max-height:90vh; background:#000; }}
            #status {{ padding:8px; font-size:14px; opacity:0.7; }}
          </style>
        </head>
        <body>
          <video id="v" autoplay playsinline muted></video>
          <div id="status">connecting…</div>
          <script>
            const statusEl = document.getElementById('status');
            const whepUrl = `http://${{location.hostname}}:{WEBRTC_PORT}/{STREAM_NAME}/whep`;

            async function start() {{
              const pc = new RTCPeerConnection();
              pc.ontrack = (ev) => {{ document.getElementById('v').srcObject = ev.streams[0]; }};
              pc.oniceconnectionstatechange = () => {{ statusEl.textContent = pc.iceConnectionState; }};
              pc.addTransceiver('video', {{ direction: 'recvonly' }});

              const offer = await pc.createOffer();
              await pc.setLocalDescription(offer);

              const resp = await fetch(whepUrl, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/sdp' }},
                body: offer.sdp,
              }});
              if (!resp.ok) {{
                statusEl.textContent = 'stream not available (' + resp.status + ')';
                setTimeout(start, 2000);
                return;
              }}
              const answerSdp = await resp.text();
              await pc.setRemoteDescription({{ type: 'answer', sdp: answerSdp }});
            }}

            start().catch(err => {{ statusEl.textContent = 'error: ' + err; setTimeout(start, 2000); }});
          </script>
        </body>
        </html>
    """)
    (WEB_DIR / "index.html").write_text(html)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass  # MediaMTX has its own log; keep supervisor.log readable


def start_webserver_thread():
    write_webpage()
    os.chdir(WEB_DIR)
    httpd = ThreadingHTTPServer(("0.0.0.0", PAGE_PORT), QuietHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


# ----------------------------------------------------------------------------
# Supervisor — the actual long-running background process
# ----------------------------------------------------------------------------

def supervise():
    """
    Runs detached in the background (spawned by `start`). Brings everything
    up, then blocks until it receives SIGTERM (from `stop`), at which point
    it tears everything down cleanly.
    """
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    f = open(SUPERVISOR_LOG, "a")
    log("Supervisor starting", f)

    mediamtx_proc = None
    httpd = None
    shutting_down = threading.Event()

    def cleanup(*_):
        if shutting_down.is_set():
            return
        shutting_down.set()
        log("Shutting down…", f)
        if httpd:
            httpd.shutdown()
        if mediamtx_proc and mediamtx_proc.poll() is None:
            mediamtx_proc.terminate()
            try:
                mediamtx_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                mediamtx_proc.kill()
        hotspot_down(f)
        if PID_FILE.exists():
            PID_FILE.unlink()
        log("Shutdown complete", f)
        f.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    try:
        hotspot_up(f)
        mediamtx_proc = start_mediamtx(f)
        httpd = start_webserver_thread()
        log(f"Webpage:       http://{hotspot_ip()}:{PAGE_PORT}/", f)
        log(f"WHEP endpoint: http://{hotspot_ip()}:{WEBRTC_PORT}/{STREAM_NAME}/whep", f)
    except Exception as e:
        log(f"Startup failed: {e}", f)
        cleanup()
        return

    # Watch the MediaMTX child; restart it if it dies unexpectedly.
    while not shutting_down.is_set():
        if mediamtx_proc.poll() is not None:
            log("MediaMTX exited unexpectedly, restarting it", f)
            mediamtx_proc = start_mediamtx(f)
        time.sleep(2)


# ----------------------------------------------------------------------------
# CLI commands
# ----------------------------------------------------------------------------

def cmd_start(_args):
    if os.geteuid() != 0:
        print("Warning: not running as root. NetworkManager hotspot changes "
              "usually need sudo — if `start` fails, re-run with sudo.")

    if read_pidfile():
        print("Already running. Use 'restart' to apply config changes.")
        return

    if not mediamtx_available():
        print(f"MediaMTX not found at {MEDIAMTX_BIN} or on PATH.")
        print("Download the arm64 build from:")
        print("  https://github.com/bluenviron/mediamtx/releases")
        print("extract it, then: sudo mv mediamtx /usr/local/bin/ && sudo chmod +x /usr/local/bin/mediamtx")
        sys.exit(1)

    BASE_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "_supervise"],
        start_new_session=True,   # fully detach from this shell
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    PID_FILE.write_text(str(proc.pid))

    print("Starting…")
    for _ in range(15):
        time.sleep(1)
        if port_open("127.0.0.1", WEBRTC_PORT) and port_open("127.0.0.1", PAGE_PORT):
            break
    cmd_status(_args)


def cmd_stop(_args):
    pid = read_pidfile()
    if not pid:
        print("Not running.")
        hotspot_down()  # defensive cleanup in case of a previous unclean shutdown
        return
    print(f"Stopping (pid {pid})…")
    os.kill(pid, signal.SIGTERM)
    for _ in range(10):
        if not pid_alive(pid):
            break
        time.sleep(1)
    else:
        os.kill(pid, signal.SIGKILL)
    print("Stopped.")


def cmd_restart(args):
    cmd_stop(args)
    time.sleep(1)
    cmd_start(args)


def cmd_status(_args):
    pid = read_pidfile()
    running = pid is not None
    print(f"Supervisor:        {'running (pid ' + str(pid) + ')' if running else 'stopped'}")
    up = hotspot_is_up()
    print(f"Hotspot:           {'up — SSID ' + SSID if up else 'down'}")
    if up:
        n = connected_client_count()
        print(f"Connected devices: {n if n >= 0 else 'unknown'}")
    mtx_up = port_open("127.0.0.1", WEBRTC_PORT)
    page_up = port_open("127.0.0.1", PAGE_PORT)
    print(f"MediaMTX/WebRTC:   {'listening on ' + str(WEBRTC_PORT) if mtx_up else 'down'}")
    print(f"Webpage:           {'listening on ' + str(PAGE_PORT) if page_up else 'down'}")
    if running and page_up:
        ip = hotspot_ip()
        print(f"\nOnce a device is connected to '{SSID}', open:")
        print(f"  http://{ip}:{PAGE_PORT}/")


def main():
    parser = argparse.ArgumentParser(description="Pi camera hotspot + low-latency livefeed")
    parser.add_argument("command",
                         choices=["start", "stop", "restart", "status", "info", "_supervise"],
                         help="start|stop|restart|status (info is an alias for status)")
    args = parser.parse_args()

    if args.command == "_supervise":
        supervise()
    elif args.command == "start":
        cmd_start(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "restart":
        cmd_restart(args)
    elif args.command in ("status", "info"):
        cmd_status(args)


if __name__ == "__main__":
    main()
