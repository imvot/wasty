import { useEffect, useRef } from "react";
import type { Capabilities } from "../api/types";
import VideoFeed from "../panels/VideoFeed";
import DriveControls from "../panels/DriveControls";
import EStop from "../panels/EStop";
import RecordControl from "../panels/RecordControl";
import RecordingBadge from "../panels/RecordingBadge";
import FullscreenButton from "../panels/FullscreenButton";

interface Props {
  caps: Capabilities;
  onBack: () => void;
}

function leaveImmersive(el: HTMLElement | null) {
  el?.classList.remove("immersive");
  document.documentElement.classList.remove("livefeed-immersive");
  const doc = document as Document & {
    webkitFullscreenElement?: Element | null;
    webkitExitFullscreen?: () => void;
  };
  if (doc.fullscreenElement || doc.webkitFullscreenElement) {
    try {
      doc.exitFullscreen?.();
      doc.webkitExitFullscreen?.();
    } catch {
      /* ignore */
    }
  }
}

export default function LivefeedPage({ caps, onBack }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const hasVideo = caps.panels.includes("video");
  const hasDrive = caps.panels.includes("drive");
  const canRecord = caps.panels.includes("recording") && caps.recording?.enabled;
  const resLabel = caps.recording
    ? `${caps.recording.width}×${caps.recording.height}`
    : "camera";

  useEffect(() => () => leaveImmersive(rootRef.current), []);

  return (
    <div className="livefeed" ref={rootRef}>
      <header className="livefeed-bar">
        <button
          type="button"
          className="back-btn"
          onClick={() => {
            leaveImmersive(rootRef.current);
            onBack();
          }}
        >
          ←
        </button>
        <h1>Livefeed</h1>
        <FullscreenButton targetRef={rootRef} />
        {canRecord && <RecordControl resolutionLabel={resLabel} />}
        {caps.panels.includes("estop") && <EStop compact />}
      </header>

      <div className={`livefeed-stage ${hasDrive ? "with-drive" : "video-only"}`}>
        {hasDrive && (
          <DriveControls
            heldThrottle={caps.drive.held_throttle}
            maxThrottle={caps.drive.max_throttle}
            stepIncrement={caps.drive.step_increment}
          />
        )}
        <div className="livefeed-video">
          {hasVideo ? (
            <>
              <VideoFeed stream={caps.stream} />
              <RecordingBadge />
            </>
          ) : (
            <div className="center-msg">Camera unavailable</div>
          )}
        </div>
      </div>
    </div>
  );
}
