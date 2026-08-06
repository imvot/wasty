export interface Capabilities {
  panels: string[];
  stream: { name: string; webrtc_port: number };
  drive: {
    held_throttle: number;
    max_throttle: number;
    step_increment: number;
  };
  recording: {
    enabled: boolean;
    directory: string;
    width: number;
    height: number;
    bitrate: number;
  };
}

export interface DriveState {
  throttle: number;
  steering: number;
  steering_angle: number;
  active_source: "manual" | "autonomy" | "none" | "estop";
  estop: boolean;
  ts: number;
}

export interface MissionState {
  state: "idle" | "search" | "approach" | "collect";
  detail: string;
  ts: number;
}

export interface Detection {
  label: string;
  confidence: number;
  cx: number;
  cy: number;
  w: number;
  h: number;
}

export interface Detections {
  items: Detection[];
  frame_ts: number;
  ts: number;
}

export interface RecordingState {
  recording: boolean;
  filename?: string | null;
  started_at?: string | null;
  path?: string | null;
  error?: string | null;
  ts?: number;
}

export type ServerMessage =
  | { type: "drive.state"; payload: DriveState }
  | { type: "mission.state"; payload: MissionState }
  | { type: "detections"; payload: Detections }
  | { type: "recording.state"; payload: RecordingState };

export type PageId = "home" | "livefeed" | "autonomy" | "status";
