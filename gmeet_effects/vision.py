"""MediaPipe wrappers: hand landmarks and person segmentation (all on-device)."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Hand:
    label: str  # "Left" / "Right" as reported by MediaPipe
    landmarks: np.ndarray  # (21, 2) normalized x, y


class HandTracker:
    def __init__(self, max_hands: int = 2, proc_width: int = 640):
        import mediapipe as mp

        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            model_complexity=0,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5,
        )
        self.proc_width = proc_width

    def process(self, frame_bgr: np.ndarray) -> list[Hand]:
        h, w = frame_bgr.shape[:2]
        if w > self.proc_width:
            small = cv2.resize(frame_bgr, (self.proc_width, int(h * self.proc_width / w)))
        else:
            small = frame_bgr
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        res = self._hands.process(rgb)
        hands: list[Hand] = []
        if res.multi_hand_landmarks:
            labels = res.multi_handedness or []
            for i, lms in enumerate(res.multi_hand_landmarks):
                pts = np.array([(p.x, p.y) for p in lms.landmark], dtype=np.float32)
                label = labels[i].classification[0].label if i < len(labels) else str(i)
                hands.append(Hand(label, pts))
        return hands

    def close(self) -> None:
        self._hands.close()


class PersonSegmenter:
    """Selfie segmentation with temporal smoothing to reduce edge flicker."""

    def __init__(self, smoothing: float = 0.5):
        import mediapipe as mp

        self._seg = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)
        self.smoothing = smoothing
        self._prev: np.ndarray | None = None

    def process(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Return a float32 person-probability mask in [0, 1] at frame resolution."""
        h, w = frame_bgr.shape[:2]
        small = cv2.resize(frame_bgr, (256, 144), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        raw = self._seg.process(rgb).segmentation_mask
        if raw is None:
            raw = np.zeros((144, 256), np.float32)
        raw = raw.astype(np.float32)
        if self._prev is not None and self._prev.shape == raw.shape:
            raw = self.smoothing * self._prev + (1.0 - self.smoothing) * raw
        self._prev = raw
        return cv2.resize(raw, (w, h), interpolation=cv2.INTER_LINEAR)

    def close(self) -> None:
        self._seg.close()


def draw_hands(img: np.ndarray, hands: list[Hand]) -> None:
    h, w = img.shape[:2]
    for hand in hands:
        pts = (hand.landmarks * (w, h)).astype(int)
        for idx, (x, y) in enumerate(pts):
            color = (0, 255, 255) if idx in (4, 12) else (0, 200, 0)
            cv2.circle(img, (int(x), int(y)), 4, color, -1, cv2.LINE_AA)
