import { useEffect, useRef, useState } from "react";
import type { Detections } from "../api/types";
import { ws } from "../api/ws";

interface Props {
  stream: { name: string; webrtc_port: number };
}

/** WebRTC (WHEP) player pulling from MediaMTX, with detection box overlay. */
export default function VideoFeed({ stream }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState("connecting…");
  const [detections, setDetections] = useState<Detections | null>(null);

  useEffect(() => ws.on("detections", (p) => setDetections(p as Detections)), []);

  useEffect(() => {
    let pc: RTCPeerConnection | null = null;
    let retry: number | undefined;
    let stopped = false;

    async function connect() {
      if (stopped) return;
      pc?.close();
      pc = new RTCPeerConnection();
      pc.ontrack = (ev) => {
        if (videoRef.current) videoRef.current.srcObject = ev.streams[0];
      };
      pc.oniceconnectionstatechange = () => {
        if (!pc) return;
        setStatus(pc.iceConnectionState);
        if (["failed", "disconnected"].includes(pc.iceConnectionState)) {
          retry = window.setTimeout(connect, 2000);
        }
      };
      pc.addTransceiver("video", { direction: "recvonly" });
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      try {
        const whepUrl = `http://${location.hostname}:${stream.webrtc_port}/${stream.name}/whep`;
        const resp = await fetch(whepUrl, {
          method: "POST",
          headers: { "Content-Type": "application/sdp" },
          body: offer.sdp,
        });
        if (!resp.ok) throw new Error(`WHEP ${resp.status}`);
        await pc.setRemoteDescription({ type: "answer", sdp: await resp.text() });
      } catch (e) {
        setStatus(`stream unavailable (${e})`);
        retry = window.setTimeout(connect, 2000);
      }
    }

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(retry);
      pc?.close();
    };
  }, [stream.name, stream.webrtc_port]);

  return (
    <div className="video-wrap">
      <video ref={videoRef} autoPlay playsInline muted />
      <div className="video-status">{status}</div>
      {detections?.items.map((d, i) => (
        <div
          key={i}
          className="det-box"
          style={{
            left: `${(d.cx - d.w / 2) * 100}%`,
            top: `${(d.cy - d.h / 2) * 100}%`,
            width: `${d.w * 100}%`,
            height: `${d.h * 100}%`,
          }}
        >
          <span>
            {d.label} {(d.confidence * 100).toFixed(0)}%
          </span>
        </div>
      ))}
    </div>
  );
}
