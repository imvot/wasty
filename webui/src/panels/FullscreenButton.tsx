import { useEffect, useState, type RefObject } from "react";

interface Props {
  targetRef: RefObject<HTMLElement | null>;
}

function isFsActive(el: HTMLElement | null): boolean {
  const doc = document as Document & {
    webkitFullscreenElement?: Element | null;
  };
  const fs = doc.fullscreenElement ?? doc.webkitFullscreenElement ?? null;
  return !!el && fs === el;
}

/** Native fullscreen when available; CSS immersive mode on iPhone Safari. */
export default function FullscreenButton({ targetRef }: Props) {
  const [active, setActive] = useState(false);

  useEffect(() => {
    const sync = () => {
      const el = targetRef.current;
      const immersive = el?.classList.contains("immersive") ?? false;
      setActive(isFsActive(el) || immersive);
    };
    document.addEventListener("fullscreenchange", sync);
    document.addEventListener("webkitfullscreenchange", sync as EventListener);
    return () => {
      document.removeEventListener("fullscreenchange", sync);
      document.removeEventListener(
        "webkitfullscreenchange",
        sync as EventListener,
      );
    };
  }, [targetRef]);

  async function toggle() {
    const el = targetRef.current;
    if (!el) return;

    const doc = document as Document & {
      webkitFullscreenElement?: Element | null;
      webkitExitFullscreen?: () => Promise<void> | void;
    };
    const anyEl = el as HTMLElement & {
      webkitRequestFullscreen?: () => Promise<void> | void;
    };

    if (isFsActive(el) || el.classList.contains("immersive")) {
      if (doc.fullscreenElement || doc.webkitFullscreenElement) {
        try {
          if (doc.exitFullscreen) await doc.exitFullscreen();
          else doc.webkitExitFullscreen?.();
        } catch {
          /* ignore */
        }
      }
      el.classList.remove("immersive");
      document.documentElement.classList.remove("livefeed-immersive");
      setActive(false);
      return;
    }

    try {
      if (anyEl.requestFullscreen) {
        await anyEl.requestFullscreen();
        setActive(true);
        return;
      }
      if (anyEl.webkitRequestFullscreen) {
        await anyEl.webkitRequestFullscreen();
        setActive(true);
        return;
      }
    } catch {
      /* fall through to immersive */
    }

    // iPhone Safari: element fullscreen is unreliable — cover the visual viewport.
    el.classList.add("immersive");
    document.documentElement.classList.add("livefeed-immersive");
    setActive(true);
  }

  return (
    <button
      type="button"
      className={`fs-btn ${active ? "active" : ""}`}
      onClick={toggle}
      title={active ? "Exit fullscreen" : "Fullscreen"}
      aria-pressed={active}
    >
      {active ? "Exit" : "Full"}
    </button>
  );
}
