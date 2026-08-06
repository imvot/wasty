import { useEffect, useState } from "react";
import type { RecordingState } from "../api/types";
import { ws } from "../api/ws";

/** Persistent on-video indicator while a training clip is being captured. */
export default function RecordingBadge() {
  const [state, setState] = useState<RecordingState>({ recording: false });
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => ws.on("recording.state", (p) => setState(p as RecordingState)), []);

  useEffect(() => {
    if (!state.recording || !state.started_at) {
      setElapsed(0);
      return;
    }
    const started = Date.parse(state.started_at);
    const tick = () =>
      setElapsed(Math.max(0, Math.floor((Date.now() - started) / 1000)));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [state.recording, state.started_at]);

  if (!state.recording) return null;

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <div className="rec-badge" role="status" aria-live="polite">
      <span className="rec-badge-dot" />
      <span>REC</span>
      <span className="rec-badge-time">
        {mm}:{ss}
      </span>
      {state.filename && <span className="rec-badge-file">{state.filename}</span>}
    </div>
  );
}
