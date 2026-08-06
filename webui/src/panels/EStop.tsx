import { useEffect, useState } from "react";
import type { DriveState } from "../api/types";
import { ws } from "../api/ws";

interface Props {
  compact?: boolean;
}

export default function EStop({ compact = false }: Props) {
  const [engaged, setEngaged] = useState(false);

  useEffect(
    () => ws.on("drive.state", (p) => setEngaged((p as DriveState).estop)),
    [],
  );

  return (
    <button
      type="button"
      className={`estop ${engaged ? "engaged" : ""} ${compact ? "compact" : ""}`}
      onClick={() => ws.send("estop", { engaged: !engaged })}
    >
      {engaged ? "RELEASE" : "E-STOP"}
    </button>
  );
}
