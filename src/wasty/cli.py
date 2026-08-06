"""wastyctl — tiny CLI talking to the running service's REST API."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _request(base: str, path: str, payload: dict | None = None) -> dict:
    url = base.rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"error: cannot reach wasty at {base} ({exc})", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="wastyctl")
    parser.add_argument(
        "--url", default="http://127.0.0.1:8080", help="wasty web service base URL"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show service status")
    estop = sub.add_parser("estop", help="engage or release the emergency stop")
    estop.add_argument("action", choices=["on", "off"])
    mission = sub.add_parser("mission", help="start or stop the autonomy mission")
    mission.add_argument("action", choices=["start", "stop"])
    args = parser.parse_args()

    if args.command == "status":
        print(json.dumps(_request(args.url, "/api/status"), indent=2))
    elif args.command == "estop":
        result = _request(args.url, "/api/estop", {"engaged": args.action == "on"})
        print(json.dumps(result))
    elif args.command == "mission":
        result = _request(args.url, "/api/mission", {"action": args.action})
        print(json.dumps(result))


if __name__ == "__main__":
    main()
