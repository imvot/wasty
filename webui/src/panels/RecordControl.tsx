import { useEffect, useState } from "react";
import type { RecordingState } from "../api/types";
import { ws } from "../api/ws";

interface Props {
  resolutionLabel: string;
}

export default function RecordControl({ resolutionLabel }: Props) {
  const [state, setState] = useState<RecordingState>({ recording: false });
  const [busy, setBusy] = useState(false);

  useEffect(
    () =>
      ws.on("recording.state", (p) => {
        setState(p as RecordingState);
        setBusy(false);
      }),
    [],
  );

  function toggle() {
    if (busy) return;
    setBusy(true);
    ws.send("recording", { action: state.recording ? "stop" : "start" });
  }

  return (
    <button
      type="button"
      className={`record-btn ${state.recording ? "recording" : ""}`}
      onClick={toggle}
      disabled={busy}
      title={`Saves ${resolutionLabel} camera MP4 (not the compressed livefeed)`}
    >
      <span className="record-dot" />
      {state.recording ? "Stop" : "Record"}
    </button>
  );
}
