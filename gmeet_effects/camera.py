"""Threaded webcam capture so frame grabbing never blocks processing."""

from __future__ import annotations

import sys
import threading
import time

import cv2
import numpy as np


class Camera:
    def __init__(self, index: int, width: int, height: int, fps: int):
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(index, backend)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open webcam #{index}")
        # MJPG lets most USB webcams deliver 720p at 30 fps.
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._frame: np.ndarray | None = None
        self._seq = 0
        self._cond = threading.Condition()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="camera", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while self._running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            with self._cond:
                self._frame = frame
                self._seq += 1
                self._cond.notify_all()

    def read(self, last_seq: int, timeout: float = 1.0) -> tuple[int, np.ndarray | None]:
        """Block until a frame newer than ``last_seq`` is available."""
        with self._cond:
            self._cond.wait_for(lambda: self._seq != last_seq or not self._running, timeout)
            return self._seq, self._frame

    def release(self) -> None:
        self._running = False
        with self._cond:
            self._cond.notify_all()
        self._thread.join(timeout=2)
        self.cap.release()


def list_cameras(max_index: int = 6) -> list[int]:
    """Probe the first few camera indices and return the ones that open."""
    found = []
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    for i in range(max_index):
        cap = cv2.VideoCapture(i, backend)
        if cap.isOpened():
            found.append(i)
        cap.release()
    return found
