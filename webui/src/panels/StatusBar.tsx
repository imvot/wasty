import { useEffect, useState } from "react";
import type { DriveState } from "../api/types";
import { ws } from "../api/ws";

interface ServiceInfo {
  state: string;
  [key: string]: unknown;
}

export default function StatusBar() {
  const [connected, setConnected] = useState(false);
  const [drive, setDrive] = useState<DriveState | null>(null);
  const [services, setServices] = useState<Record<string, ServiceInfo>>({});

  useEffect(() => ws.onStatus(setConnected), []);
  useEffect(() => ws.on("drive.state", (p) => setDrive(p as DriveState)), []);

  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const r = await fetch("/api/status");
        const data = await r.json();
        if (!stop) setServices(data.services ?? {});
      } catch {
        /* backend unreachable; ws status dot already shows it */
      }
      if (!stop) setTimeout(poll, 5000);
    }
    poll();
    return () => { stop = true; };
  }, []);

  const unhealthy = Object.entries(services).filter(
    ([, s]) => s.state !== "running",
  );

  return (
    <footer className="statusbar">
      <span className={`dot ${connected ? "ok" : "bad"}`} />
      <span>{connected ? "link" : "no link"}</span>
      {drive && (
        <>
          <span>thr {drive.throttle.toFixed(2)}</span>
          <span>steer {drive.steering.toFixed(2)}</span>
          <span>src {drive.active_source}</span>
        </>
      )}
      <span className="spacer" />
      {unhealthy.length > 0
        ? unhealthy.map(([name, s]) => (
            <span key={name} className="svc-bad">
              {name}: {s.state}
            </span>
          ))
        : <span className="svc-ok">all services running</span>}
    </footer>
  );
}
