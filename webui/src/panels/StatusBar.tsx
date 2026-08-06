import { useEffect, useState } from "react";
import type { DriveState } from "../api/types";
import { ws } from "../api/ws";

interface ServiceInfo {
  state: string;
  [key: string]: unknown;
}

interface Props {
  expanded?: boolean;
}

export default function StatusBar({ expanded = false }: Props) {
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
        /* ignore */
      }
      if (!stop) setTimeout(poll, 5000);
    }
    poll();
    return () => {
      stop = true;
    };
  }, []);

  const unhealthy = Object.entries(services).filter(([, s]) => s.state !== "running");

  if (expanded) {
    return (
      <div className="status-expanded">
        <div className="status-row">
          <span className={`dot ${connected ? "ok" : "bad"}`} />
          <strong>{connected ? "Link up" : "No link"}</strong>
        </div>
        {drive && (
          <dl className="status-dl">
            <div>
              <dt>Throttle</dt>
              <dd>{drive.throttle.toFixed(2)}</dd>
            </div>
            <div>
              <dt>Steering</dt>
              <dd>{drive.steering.toFixed(2)}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>{drive.active_source}</dd>
            </div>
            <div>
              <dt>E-stop</dt>
              <dd>{drive.estop ? "engaged" : "clear"}</dd>
            </div>
          </dl>
        )}
        <h2>Services</h2>
        <ul className="svc-list">
          {Object.entries(services).map(([name, s]) => (
            <li key={name} className={s.state === "running" ? "ok" : "bad"}>
              <span>{name}</span>
              <span>{s.state}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

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
      {unhealthy.length > 0 ? (
        unhealthy.map(([name, s]) => (
          <span key={name} className="svc-bad">
            {name}: {s.state}
          </span>
        ))
      ) : (
        <span className="svc-ok">all services running</span>
      )}
    </footer>
  );
}
