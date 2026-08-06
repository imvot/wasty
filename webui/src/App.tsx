import { useEffect, useMemo, useState } from "react";
import type { Capabilities, PageId } from "./api/types";
import { ws } from "./api/ws";
import HomePage from "./pages/HomePage";
import LivefeedPage from "./pages/LivefeedPage";
import AutonomyPage from "./pages/AutonomyPage";
import StatusPage from "./pages/StatusPage";

function pageFromHash(): PageId {
  const raw = location.hash.replace(/^#\/?/, "") || "home";
  if (raw === "livefeed" || raw === "autonomy" || raw === "status") return raw;
  return "home";
}

export default function App() {
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<PageId>(pageFromHash);

  useEffect(() => {
    ws.connect();
    fetch("/api/capabilities")
      .then((r) => r.json())
      .then((data: Capabilities) => {
        setCaps({
          ...data,
          drive: data.drive ?? {
            held_throttle: 0.6,
            max_throttle: 1.0,
            step_increment: 0.2,
          },
          recording: data.recording ?? {
            enabled: false,
            directory: "",
            width: 1280,
            height: 720,
            bitrate: 8_000_000,
          },
        });
      })
      .catch((e) => setError(String(e)));
    return () => ws.close();
  }, []);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  function go(next: PageId) {
    location.hash = next === "home" ? "" : `#/${next}`;
    setPage(next);
  }

  const pages = useMemo(() => {
    if (!caps) return [];
    const has = (p: string) => caps.panels.includes(p);
    const list: { id: PageId; title: string; blurb: string }[] = [];
    if (has("video") || has("drive")) {
      list.push({
        id: "livefeed",
        title: "Livefeed",
        blurb: "Camera + held/step drive controls",
      });
    }
    if (has("autonomy")) {
      list.push({
        id: "autonomy",
        title: "Autonomy",
        blurb: "Start and stop trash-collection missions",
      });
    }
    list.push({
      id: "status",
      title: "Status",
      blurb: "Link health, drive telemetry, service states",
    });
    return list;
  }, [caps]);

  if (error) return <div className="center-msg">Cannot reach robot: {error}</div>;
  if (!caps) return <div className="center-msg">Connecting…</div>;

  return (
    <div className="app">
      {page === "home" && <HomePage pages={pages} onOpen={go} />}
      {page === "livefeed" && (
        <LivefeedPage caps={caps} onBack={() => go("home")} />
      )}
      {page === "autonomy" && <AutonomyPage onBack={() => go("home")} />}
      {page === "status" && <StatusPage onBack={() => go("home")} />}
    </div>
  );
}
