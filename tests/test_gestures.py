import numpy as np

from gmeet_effects.gestures import SnapDetector
from gmeet_effects.vision import Hand


def make_hand(gap: float, reach: float) -> Hand:
    """Synthetic hand in square-ish coords: palm length 0.1 (wrist->middle MCP)."""
    pts = np.zeros((21, 2), np.float32)
    wrist = np.array([0.5, 0.8])
    pts[0] = wrist
    pts[9] = wrist + [0, -0.1]
    pts[12] = wrist + [0, -0.1 * reach]
    pts[4] = pts[12] + [0.1 * gap, 0]
    pts[:, 0] /= 16 / 9  # detector rescales x by the aspect ratio
    return Hand("Right", pts)


def run(seq, detector=None):
    d = detector or SnapDetector()
    return [d.update(t, [make_hand(g, r)]) for t, g, r in seq]


def test_snap_detected():
    seq = [(0.00, 0.2, 1.8), (0.03, 0.2, 1.8), (0.07, 0.4, 1.5), (0.10, 0.9, 1.2)]
    assert run(seq)[-1] is True


def test_opening_hand_is_not_a_snap():
    # Fingers separate but middle finger extends (reach grows) -> no snap.
    seq = [(0.00, 0.2, 1.6), (0.05, 0.5, 1.8), (0.10, 0.9, 2.0)]
    assert not any(run(seq))


def test_slow_release_is_not_a_snap():
    seq = [(0.0, 0.2, 1.8), (0.5, 0.4, 1.5), (1.0, 0.9, 1.2)]
    assert not any(run(seq))


def test_cooldown():
    d = SnapDetector()
    snap = [(0.00, 0.2, 1.8), (0.10, 0.9, 1.2)]
    assert run(snap, d)[-1]
    again = [(t + 0.3, g, r) for t, g, r in snap]
    assert not any(run(again, d))
    later = [(t + 2.0, g, r) for t, g, r in snap]
    assert run(later, d)[-1]
