import type { Capabilities } from "../api/types";
import VideoFeed from "../panels/VideoFeed";
import DriveControls from "../panels/DriveControls";
import EStop from "../panels/EStop";
import RecordControl from "../panels/RecordControl";
import RecordingBadge from "../panels/RecordingBadge";

interface Props {
  caps: Capabilities;
  onBack: () => void;
}

export default function LivefeedPage({ caps, onBack }: Props) {
  const hasVideo = caps.panels.includes("video");
  const hasDrive = caps.panels.includes("drive");
  const canRecord = caps.panels.includes("recording") && caps.recording?.enabled;
  const resLabel = caps.recording
    ? `${caps.recording.width}×${caps.recording.height}`
    : "camera";

  return (
    <div className="livefeed">
      <header className="livefeed-bar">
        <button type="button" className="back-btn" onClick={onBack}>
          ←
        </button>
        <h1>Livefeed</h1>
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
