"""Clean-plate background used to fill the area hidden behind the user."""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np


class BackgroundModel:
    """Holds a captured clean plate and/or an adaptively learned background.

    * ``capture`` stores a median of frames taken while the user is out of shot.
    * With ``adaptive`` enabled, pixels not covered by the person keep refreshing
      the plate so slow lighting changes do not leave a visible "ghost" patch.
    * Without a captured plate, regions never seen are filled by inpainting.
    """

    def __init__(self, rate: float = 0.05):
        self.rate = rate
        self.captured = False
        self._image: np.ndarray | None = None  # float32 BGR
        self._seen: np.ndarray | None = None  # float32 0..1 coverage
        self._filled: np.ndarray | None = None
        self._filled_at = 0.0

    @property
    def available(self) -> bool:
        return self._image is not None

    def reset(self) -> None:
        self.captured = False
        self._image = self._seen = self._filled = None

    def capture(self, frames: list[np.ndarray]) -> None:
        stack = np.stack(frames).astype(np.float32)
        self._image = np.median(stack, axis=0).astype(np.float32)
        self._seen = np.ones(self._image.shape[:2], np.float32)
        self._filled = self._image
        self.captured = True

    def set_image(self, img: np.ndarray) -> None:
        self.capture([img])

    def update(self, frame: np.ndarray, person: np.ndarray, adaptive: bool) -> None:
        if self._image is not None and self._image.shape != frame.shape:
            self._image = cv2.resize(self._image, (frame.shape[1], frame.shape[0]))
            self._seen = cv2.resize(self._seen, (frame.shape[1], frame.shape[0]))
            self._filled = None
        if self._image is None:
            self._image = frame.astype(np.float32)
            self._seen = np.zeros(frame.shape[:2], np.float32)
        if self.captured and not adaptive:
            return
        # Only learn from pixels that are confidently background.
        clear = (person < 0.1).astype(np.float32)
        clear = cv2.erode(clear, np.ones((15, 15), np.uint8))
        rate = self.rate if self.captured else max(self.rate, 0.2)
        w = (clear * rate)[..., None]
        self._image += (frame.astype(np.float32) - self._image) * w
        np.maximum(self._seen, clear, out=self._seen)

    def get(self) -> np.ndarray | None:
        if self._image is None:
            return None
        if self.captured or self._seen.min() > 0.5:
            return self._image
        now = time.monotonic()
        if self._filled is None or now - self._filled_at > 1.0:
            # Inpaint never-seen areas at low resolution (fast), then upscale.
            h, w = self._image.shape[:2]
            small = cv2.resize(self._image, (w // 4, h // 4)).clip(0, 255).astype(np.uint8)
            hole = cv2.resize((self._seen < 0.5).astype(np.uint8) * 255, (w // 4, h // 4))
            fill = cv2.inpaint(small, hole, 5, cv2.INPAINT_TELEA)
            fill = cv2.resize(fill, (w, h)).astype(np.float32)
            m = (self._seen >= 0.5).astype(np.float32)[..., None]
            self._filled = self._image * m + fill * (1 - m)
            self._filled_at = now
        return self._filled

    def save(self, path: Path) -> None:
        if self._image is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(path), self._image.clip(0, 255).astype(np.uint8))

    def load(self, path: Path) -> bool:
        img = cv2.imread(str(path)) if Path(path).exists() else None
        if img is None:
            return False
        self.set_image(img)
        return True
