"""Virtual webcam output (Unity Capture on Windows) via pyvirtualcam."""

from __future__ import annotations

import cv2
import numpy as np


class VirtualCamera:
    def __init__(self, width: int, height: int, fps: int, backend: str = "unitycapture",
                 device: str = ""):
        import pyvirtualcam

        kwargs = {"width": width, "height": height, "fps": fps,
                  "fmt": pyvirtualcam.PixelFormat.RGB}
        if backend and backend != "auto":
            kwargs["backend"] = backend
        if device:
            kwargs["device"] = device
        self.cam = pyvirtualcam.Camera(**kwargs)
        self.size = (width, height)

    @property
    def device(self) -> str:
        return self.cam.device

    def send(self, frame_bgr: np.ndarray) -> None:
        if (frame_bgr.shape[1], frame_bgr.shape[0]) != self.size:
            frame_bgr = cv2.resize(frame_bgr, self.size)
        self.cam.send(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))

    def close(self) -> None:
        self.cam.close()
