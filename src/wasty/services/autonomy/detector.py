"""Detector interface. Swapping the stub for a real model (ONNX/NCNN on the
Pi 5 CPU) only touches this file: implement Detector, register it in
create_detector()."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from ...core.messages import Detection


class Detector(Protocol):
    def load(self) -> None:
        """Called once inside the inference worker process."""
        ...

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """frame: lores RGB uint8 array (H, W, 3). Returns detections."""
        ...


class StubDetector:
    """Placeholder: never detects anything. Replace with a real model."""

    def load(self) -> None:
        pass

    def detect(self, frame: np.ndarray) -> list[Detection]:
        return []


class MockBlobDetector:
    """Dev helper: finds the bright green square the MockCamera draws, so the
    whole autonomy loop can be exercised end-to-end without a model."""

    def load(self) -> None:
        pass

    def detect(self, frame: np.ndarray) -> list[Detection]:
        h, w = frame.shape[:2]
        mask = (
            (frame[:, :, 1] > 180)
            & (frame[:, :, 0] < 100)
            & (frame[:, :, 2] < 150)
        )
        ys, xs = np.nonzero(mask)
        if len(xs) < 50:
            return []
        x0, x1 = xs.min(), xs.max()
        y0, y1 = ys.min(), ys.max()
        return [
            Detection(
                label="trash",
                confidence=0.9,
                cx=(x0 + x1) / 2 / w,
                cy=(y0 + y1) / 2 / h,
                w=(x1 - x0) / w,
                h=(y1 - y0) / h,
            )
        ]


def create_detector(name: str) -> Detector:
    detectors = {
        "stub": StubDetector,
        "mock-blob": MockBlobDetector,
    }
    if name not in detectors:
        raise ValueError(f"unknown detector '{name}' (available: {list(detectors)})")
    return detectors[name]()
