import { useEffect, useRef, useState } from "react";
import { ws } from "../api/ws";

const SEND_HZ = 10;
const MODE_KEY = "wasty.driveMode";

type Mode = "held" | "step";
type HoldKey = "fwd" | "rev" | "left" | "right";

interface Props {
  heldThrottle: number;
  maxThrottle: number;
  stepIncrement: number;
}

function clamp(x: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, x));
}

/**
 * Held mode: hold throttle/steer buttons. Optional boost toggle → max throttle.
 * Step mode: each throttle tap nudges a retained value; steer is still hold-to-steer.
 *
 * Layout: throttle column on the left, steering on the right (landscape-first).
 */
export default function DriveControls({
  heldThrottle,
  maxThrottle,
  stepIncrement,
}: Props) {
  const [mode, setMode] = useState<Mode>(() => {
    const saved = localStorage.getItem(MODE_KEY);
    return saved === "step" ? "step" : "held";
  });
  const [boost, setBoost] = useState(false);
  const [stepThrottle, setStepThrottle] = useState(0);
  const held = useRef<Record<HoldKey, boolean>>({
    fwd: false,
    rev: false,
    left: false,
    right: false,
  });
  const modeRef = useRef(mode);
  const boostRef = useRef(boost);
  const stepRef = useRef(stepThrottle);
  const timer = useRef<number | undefined>(undefined);
  const [, bump] = useState(0);

  modeRef.current = mode;
  boostRef.current = boost;
  stepRef.current = stepThrottle;

  function compute(): { throttle: number; steering: number } {
    const { fwd, rev, left, right } = held.current;
    const steering = (left ? -1 : 0) + (right ? 1 : 0);

    if (modeRef.current === "step") {
      return { throttle: stepRef.current, steering };
    }

    let throttle = 0;
    if (fwd && !rev) throttle = boostRef.current ? maxThrottle : heldThrottle;
    else if (rev && !fwd) throttle = -(boostRef.current ? maxThrottle : heldThrottle);
    return { throttle, steering };
  }

  function needsHeartbeat(): boolean {
    const { fwd, rev, left, right } = held.current;
    if (left || right) return true;
    if (modeRef.current === "held") return fwd || rev;
    return stepRef.current !== 0 || fwd || rev;
  }

  function syncHeartbeat() {
    const need = needsHeartbeat();
    if (need && timer.current === undefined) {
      timer.current = window.setInterval(() => {
        ws.send("drive", compute());
      }, 1000 / SEND_HZ);
      ws.send("drive", compute());
    } else if (!need && timer.current !== undefined) {
      window.clearInterval(timer.current);
      timer.current = undefined;
      ws.send("drive", { throttle: 0, steering: 0 });
    }
    bump((n) => n + 1);
  }

  function setHeld(key: HoldKey, value: boolean) {
    if (held.current[key] === value) return;
    held.current[key] = value;
    syncHeartbeat();
  }

  function onThrottleTap(dir: 1 | -1) {
    if (modeRef.current !== "step") return;
    const next = clamp(
      stepRef.current + dir * stepIncrement,
      -maxThrottle,
      maxThrottle,
    );
    // Snap near-zero so deadman can release cleanly.
    const snapped = Math.abs(next) < stepIncrement / 2 ? 0 : next;
    stepRef.current = snapped;
    setStepThrottle(snapped);
    syncHeartbeat();
  }

  function switchMode(next: Mode) {
    setMode(next);
    localStorage.setItem(MODE_KEY, next);
    held.current = { fwd: false, rev: false, left: false, right: false };
    if (next === "held") {
      stepRef.current = 0;
      setStepThrottle(0);
    }
    if (timer.current !== undefined) {
      window.clearInterval(timer.current);
      timer.current = undefined;
    }
    ws.send("drive", { throttle: 0, steering: 0 });
    bump((n) => n + 1);
  }

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.repeat) return;
      if (e.code === "KeyB") {
        setBoost((b) => !b);
        return;
      }
      if (e.code === "KeyM") {
        switchMode(modeRef.current === "held" ? "step" : "held");
        return;
      }
      if (modeRef.current === "step" && (e.code === "KeyW" || e.code === "ArrowUp")) {
        e.preventDefault();
        onThrottleTap(1);
        return;
      }
      if (modeRef.current === "step" && (e.code === "KeyS" || e.code === "ArrowDown")) {
        e.preventDefault();
        onThrottleTap(-1);
        return;
      }
      const map: Record<string, HoldKey> = {
        KeyW: "fwd",
        ArrowUp: "fwd",
        KeyS: "rev",
        ArrowDown: "rev",
        KeyA: "left",
        ArrowLeft: "left",
        KeyD: "right",
        ArrowRight: "right",
      };
      const k = map[e.code];
      if (k) {
        e.preventDefault();
        setHeld(k, true);
      }
    };
    const up = (e: KeyboardEvent) => {
      const map: Record<string, HoldKey> = {
        KeyW: "fwd",
        ArrowUp: "fwd",
        KeyS: "rev",
        ArrowDown: "rev",
        KeyA: "left",
        ArrowLeft: "left",
        KeyD: "right",
        ArrowRight: "right",
      };
      const k = map[e.code];
      if (k && modeRef.current === "held") {
        e.preventDefault();
        setHeld(k, false);
      } else if (k === "left" || k === "right") {
        e.preventDefault();
        setHeld(k, false);
      }
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      if (timer.current !== undefined) {
        window.clearInterval(timer.current);
        ws.send("drive", { throttle: 0, steering: 0 });
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [heldThrottle, maxThrottle, stepIncrement]);

  function holdBtn(key: HoldKey, label: string) {
    return (
      <button
        type="button"
        className={`pad-btn ${held.current[key] ? "active" : ""}`}
        onPointerDown={(e) => {
          e.preventDefault();
          (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
          setHeld(key, true);
        }}
        onPointerUp={() => setHeld(key, false)}
        onPointerCancel={() => setHeld(key, false)}
        onContextMenu={(e) => e.preventDefault()}
      >
        {label}
      </button>
    );
  }

  function stepBtn(dir: 1 | -1, label: string) {
    return (
      <button
        type="button"
        className="pad-btn"
        onPointerDown={(e) => {
          e.preventDefault();
          onThrottleTap(dir);
        }}
        onContextMenu={(e) => e.preventDefault()}
      >
        {label}
      </button>
    );
  }

  return (
    <>
      <div className="drive-toolbar">
        <div className="mode-toggle" role="group" aria-label="Drive mode">
          <button
            type="button"
            className={mode === "held" ? "active" : ""}
            onClick={() => switchMode("held")}
          >
            Held
          </button>
          <button
            type="button"
            className={mode === "step" ? "active" : ""}
            onClick={() => switchMode("step")}
          >
            Step
          </button>
        </div>
        {mode === "held" && (
          <button
            type="button"
            className={`boost-btn ${boost ? "active" : ""}`}
            onClick={() => setBoost((b) => !b)}
          >
            Boost
          </button>
        )}
        {mode === "step" && (
          <span className="step-readout">thr {stepThrottle.toFixed(1)}</span>
        )}
      </div>

      <aside className="pad-col pad-throttle" aria-label="Throttle">
        {mode === "held" ? holdBtn("fwd", "▲") : stepBtn(1, "▲")}
        {mode === "held" ? holdBtn("rev", "▼") : stepBtn(-1, "▼")}
      </aside>

      <aside className="pad-col pad-steer" aria-label="Steering">
        {holdBtn("left", "◀")}
        {holdBtn("right", "▶")}
      </aside>
    </>
  );
}
