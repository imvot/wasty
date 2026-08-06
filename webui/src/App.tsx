import { useEffect, useState } from "react";
import type { Capabilities } from "./api/types";
import { ws } from "./api/ws";
import VideoFeed from "./panels/VideoFeed";
import DriveControls from "./panels/DriveControls";
import EStop from "./panels/EStop";
import AutonomyGo from "./panels/AutonomyGo";
import StatusBar from "./panels/StatusBar";

export default function App() {
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ws.connect();
    fetch("/api/capabilities")
      .then((r) => r.json())
      .then(setCaps)
      .catch((e) => setError(String(e)));
    return () => ws.close();
  }, []);

  if (error) return <div className="center-msg">Cannot reach robot: {error}</div>;
  if (!caps) return <div className="center-msg">Connecting…</div>;

  const has = (panel: string) => caps.panels.includes(panel);

  return (
    <div className="app">
      <main className="stage">
        {has("video") && <VideoFeed stream={caps.stream} />}
        <div className="overlay top-left">{has("autonomy") && <AutonomyGo />}</div>
        <div className="overlay top-right">{has("estop") && <EStop />}</div>
        <div className="overlay bottom">{has("drive") && <DriveControls />}</div>
      </main>
      {has("status") && <StatusBar />}
    </div>
  );
}
