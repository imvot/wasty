import { useEffect, useRef, useState } from "react";
import { ws } from "../api/ws";

const SEND_HZ = 10; // must beat the drive service's manual deadman timeout
const THROTTLE = 0.5;

/** Hold-to-drive buttons + WASD/arrow keys. Commands stream while any input
 * is active; releasing everything sends one neutral command and stops the
 * stream, letting the robot's deadman take over if the link drops. */
export default function DriveControls() {
  const held = useRef({ fwd: false, rev: false, left: false, right: false });
  const timer = useRef<number | undefined>(undefined);
  const [, forceRender] = useState(0);

  function current(): { throttle: number; steering: number } {
    const { fwd, rev, left, right } = held.current;
    return {
      throttle: (fwd ? THROTTLE : 0) + (rev ? -THROTTLE : 0),
      steering: (left ? -1 : 0) + (right ? 1 : 0),
    };
  }

  function update() {
    const anyHeld = Object.values(held.current).some(Boolean);
    if (anyHeld && timer.current === undefined) {
      timer.current = window.setInterval(
        () => ws.send("drive", current()),
        1000 / SEND_HZ,
      );
    } else if (!anyHeld && timer.current !== undefined) {
      window.clearInterval(timer.current);
      timer.current = undefined;
      ws.send("drive", { throttle: 0, steering: 0 });
    }
    forceRender((n) => n + 1);
  }

  function set(key: keyof typeof held.current, value: boolean) {
    if (held.current[key] === value) return;
    held.current[key] = value;
    update();
  }

  useEffect(() => {
    const keymap: Record<string, keyof typeof held.current> = {
      KeyW: "fwd", ArrowUp: "fwd",
      KeyS: "rev", ArrowDown: "rev",
      KeyA: "left", ArrowLeft: "left",
      KeyD: "right", ArrowRight: "right",
    };
    const down = (e: KeyboardEvent) => {
      const k = keymap[e.code];
      if (k) { e.preventDefault(); set(k, true); }
    };
    const up = (e: KeyboardEvent) => {
      const k = keymap[e.code];
      if (k) { e.preventDefault(); set(k, false); }
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      if (timer.current !== undefined) window.clearInterval(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const btn = (key: keyof typeof held.current, label: string) => (
    <button
      className={`drive-btn ${held.current[key] ? "active" : ""}`}
      onPointerDown={(e) => { e.preventDefault(); set(key, true); }}
      onPointerUp={() => set(key, false)}
      onPointerLeave={() => set(key, false)}
      onContextMenu={(e) => e.preventDefault()}
    >
      {label}
    </button>
  );

  return (
    <div className="drive-pad">
      <div className="drive-row">{btn("fwd", "▲")}</div>
      <div className="drive-row">
        {btn("left", "◀")}
        {btn("rev", "▼")}
        {btn("right", "▶")}
      </div>
    </div>
  );
}
