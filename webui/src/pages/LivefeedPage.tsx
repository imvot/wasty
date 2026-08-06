import type { Capabilities } from "../api/types";
import VideoFeed from "../panels/VideoFeed";
import DriveControls from "../panels/DriveControls";
import EStop from "../panels/EStop";

interface Props {
  caps: Capabilities;
  onBack: () => void;
}

export default function LivefeedPage({ caps, onBack }: Props) {
  const hasVideo = caps.panels.includes("video");
  const hasDrive = caps.panels.includes("drive");

  return (
    <div className="livefeed">
      <header className="livefeed-bar">
        <button type="button" className="back-btn" onClick={onBack}>
          ←
        </button>
        <h1>Livefeed</h1>
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
            <VideoFeed stream={caps.stream} />
          ) : (
            <div className="center-msg">Camera unavailable</div>
          )}
        </div>
      </div>
    </div>
  );
}
