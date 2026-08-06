import { useEffect, useState } from "react";
import type { MissionState } from "../api/types";
import { ws } from "../api/ws";

export default function AutonomyGo() {
  const [mission, setMission] = useState<MissionState | null>(null);
  const active = mission != null && mission.state !== "idle";

  useEffect(
    () => ws.on("mission.state", (p) => setMission(p as MissionState)),
    [],
  );

  return (
    <div className="autonomy">
      <button
        className={`go-btn ${active ? "active" : ""}`}
        onClick={() => ws.send("mission", { action: active ? "stop" : "start" })}
      >
        {active ? "STOP" : "GO"}
      </button>
      {active && <span className="mission-state">{mission!.state}</span>}
    </div>
  );
}
