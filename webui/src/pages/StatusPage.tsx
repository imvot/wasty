import StatusBar from "../panels/StatusBar";
import EStop from "../panels/EStop";

interface Props {
  onBack: () => void;
}

export default function StatusPage({ onBack }: Props) {
  return (
    <div className="page">
      <header className="page-bar">
        <button type="button" className="back-btn" onClick={onBack}>
          ←
        </button>
        <h1>Status</h1>
        <EStop />
      </header>
      <div className="page-body status-page">
        <StatusBar expanded />
      </div>
    </div>
  );
}
