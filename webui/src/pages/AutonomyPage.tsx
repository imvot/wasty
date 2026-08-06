import AutonomyGo from "../panels/AutonomyGo";
import EStop from "../panels/EStop";

interface Props {
  onBack: () => void;
}

export default function AutonomyPage({ onBack }: Props) {
  return (
    <div className="page">
      <header className="page-bar">
        <button type="button" className="back-btn" onClick={onBack}>
          ←
        </button>
        <h1>Autonomy</h1>
        <EStop />
      </header>
      <div className="page-body autonomy-page">
        <p className="page-lead">
          Start a collection mission. The car searches for trash, approaches, and
          collects. Manual drive on Livefeed always overrides; E-STOP aborts.
        </p>
        <AutonomyGo />
      </div>
    </div>
  );
}
