"""Inference worker: runs the detector in a separate process so CPU-heavy
models never block the asyncio control loop.

Latest-frame-wins: the parent only submits when the input queue is empty,
so the worker always processes the freshest frame and never builds a backlog.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import queue
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


def _worker_main(detector_name: str, frame_q: mp.Queue, result_q: mp.Queue) -> None:
    from .detector import create_detector

    detector = create_detector(detector_name)
    detector.load()
    while True:
        item = frame_q.get()
        if item is None:
            return
        frame_ts, frame = item
        try:
            detections = detector.detect(frame)
        except Exception:  # keep the worker alive on a bad frame
            logging.getLogger(__name__).exception("detector failed")
            continue
        result_q.put((frame_ts, [d.model_dump() for d in detections]))


class InferenceWorker:
    def __init__(self, detector_name: str):
        self.detector_name = detector_name
        ctx = mp.get_context("spawn")
        self._frame_q: mp.Queue = ctx.Queue(maxsize=1)
        self._result_q: mp.Queue = ctx.Queue(maxsize=4)
        self._proc = ctx.Process(
            target=_worker_main,
            args=(detector_name, self._frame_q, self._result_q),
            daemon=True,
        )

    def start(self) -> None:
        self._proc.start()
        log.info("inference worker started (pid %d, detector=%s)",
                 self._proc.pid, self.detector_name)

    def submit(self, frame: np.ndarray, frame_ts: float) -> bool:
        """Offer a frame; skipped if the worker is still busy with the last one."""
        try:
            self._frame_q.put_nowait((frame_ts, frame))
            return True
        except queue.Full:
            return False

    def poll_results(self) -> list[tuple[float, list[dict[str, Any]]]]:
        results = []
        while True:
            try:
                results.append(self._result_q.get_nowait())
            except queue.Empty:
                return results

    @property
    def alive(self) -> bool:
        return self._proc.is_alive()

    def stop(self) -> None:
        try:
            self._frame_q.put_nowait(None)
        except queue.Full:
            pass
        self._proc.join(timeout=2)
        if self._proc.is_alive():
            self._proc.terminate()
