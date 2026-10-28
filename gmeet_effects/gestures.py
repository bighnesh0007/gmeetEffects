"""Finger-snap detection from MediaPipe hand landmarks.

A snap has a characteristic shape in landmark space:

1. *Primed*: the middle fingertip presses against the thumb tip.
2. *Release*: within a fraction of a second the middle finger slips off the
   thumb and slams down into the palm, so the thumb-to-middle-tip distance
   jumps up while the middle-tip-to-wrist distance drops.

Distances are normalised by palm size (wrist -> middle MCP) so detection is
independent of how far the hand is from the camera. Simply opening the hand
increases the thumb/middle distance too, but it *extends* the middle finger
rather than curling it, which the curl check rejects.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

WRIST, THUMB_TIP, MIDDLE_MCP, MIDDLE_TIP = 0, 4, 9, 12


@dataclass
class SnapParams:
    pinch_threshold: float = 0.35  # thumb-middle distance (palm units) to count as primed
    release_threshold: float = 0.60  # distance that counts as released
    min_curl_drop: float = 0.15  # how much the middle tip must move toward the wrist
    max_snap_time: float = 0.35  # seconds from primed to released
    cooldown: float = 1.2
    sensitivity: float = 1.0  # >1 = easier to trigger


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(math.hypot(a[0] - b[0], a[1] - b[1]))


def hand_metrics(landmarks: np.ndarray, aspect: float = 16 / 9) -> tuple[float, float]:
    """Return (thumb-middle gap, middle-tip-to-wrist reach), both in palm units."""
    pts = landmarks * np.array([aspect, 1.0], dtype=np.float32)  # undo non-square normalisation
    palm = _dist(pts[WRIST], pts[MIDDLE_MCP])
    if palm < 1e-6:
        return float("nan"), float("nan")
    return _dist(pts[THUMB_TIP], pts[MIDDLE_TIP]) / palm, _dist(pts[MIDDLE_TIP], pts[WRIST]) / palm


class SnapDetector:
    def __init__(self, params: SnapParams | None = None, aspect: float = 16 / 9):
        self.params = params or SnapParams()
        self.aspect = aspect
        self._history: dict[str, deque] = {}
        self._last_snap = -1e9
        self.last_gap: float | None = None

    def update(self, t: float, hands) -> bool:
        """Feed the hands detected at time ``t``; return True when a snap completes."""
        p = self.params
        s = max(0.3, p.sensitivity)
        pinch = p.pinch_threshold * s
        release = p.release_threshold / s
        curl = p.min_curl_drop / s

        seen = set()
        snapped = False
        for hand in hands:
            seen.add(hand.label)
            gap, reach = hand_metrics(hand.landmarks, self.aspect)
            if math.isnan(gap):
                continue
            self.last_gap = gap
            hist = self._history.setdefault(hand.label, deque(maxlen=30))
            hist.append((t, gap, reach))
            while hist and t - hist[0][0] > p.max_snap_time:
                hist.popleft()
            if t - self._last_snap < p.cooldown or gap < release:
                continue
            for t0, gap0, reach0 in hist:
                if gap0 <= pinch and t - t0 <= p.max_snap_time and reach0 - reach >= curl:
                    snapped = True
                    break
            if snapped:
                self._last_snap = t
                hist.clear()
                break
        for label in list(self._history):
            if label not in seen:
                del self._history[label]
        return snapped
