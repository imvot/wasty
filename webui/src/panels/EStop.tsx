import { useEffect, useState } from "react";
import type { DriveState } from "../api/types";
import { ws } from "../api/ws";

export default function EStop() {
  const [engaged, setEngaged] = useState(false);

  useEffect(
    () => ws.on("drive.state", (p) => setEngaged((p as DriveState).estop)),
    [],
  );

  return (
    <button
      className={`estop ${engaged ? "engaged" : ""}`}
      onClick={() => ws.send("estop", { engaged: !engaged })}
    >
      {engaged ? "RELEASE E-STOP" : "E-STOP"}
    </button>
  );
}
