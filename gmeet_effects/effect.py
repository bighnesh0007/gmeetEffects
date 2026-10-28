"""Disintegration / reassembly effect and frame compositing."""

from __future__ import annotations

import enum

import cv2
import numpy as np

from .config import Settings
from .particles import ParticleSystem


class State(enum.Enum):
    VISIBLE = "visible"
    DISSOLVING = "dissolving"
    HIDDEN = "hidden"
    ASSEMBLING = "assembling"


class DisintegrationEffect:
    def __init__(self, settings: Settings, seed: int | None = None):
        self.settings = settings
        self.state = State.VISIBLE
        self.particles = ParticleSystem(settings.max_particles, seed)
        self.rng = np.random.default_rng(seed)
        self._t0 = 0.0
        self._prev_p = 0.0
        self._prev_front = 0.0
        self._last_t: float | None = None
        self._thr: np.ndarray | None = None
        self._pending: State | None = None

    # ------------------------------------------------------------------ control
    def toggle(self) -> State:
        """Snap action: vanish when visible, reappear when hidden."""
        if self.state == State.VISIBLE:
            self._pending = State.DISSOLVING
        elif self.state == State.HIDDEN:
            self._pending = State.ASSEMBLING
        return self._pending or self.state

    def reset(self) -> None:
        self.state = State.VISIBLE
        self._pending = None
        self.particles.clear()

    @property
    def progress(self) -> float:
        return float(np.clip(self._prev_p, 0, 1))

    # ---------------------------------------------------------------- internals
    def _threshold_map(self, mask: np.ndarray) -> np.ndarray:
        """Per-pixel dissolve order: downwind side first, broken up by noise."""
        h, w = mask.shape
        ys, xs = np.nonzero(mask > 0.5)
        if len(xs):
            x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        else:
            x0, x1, y0, y1 = 0, w - 1, 0, h - 1
        wx, wy = self.settings.wind_vector
        gx = (np.arange(w, dtype=np.float32) - x0) / max(1, x1 - x0)
        gy = (np.arange(h, dtype=np.float32) - y0) / max(1, y1 - y0)
        proj = wx * gx[None, :] + wy * gy[:, None]
        lo = min(0.0, wx) + min(0.0, wy)
        hi = max(0.0, wx) + max(0.0, wy)
        grad = 1.0 - (proj - lo) / max(1e-6, hi - lo)  # downwind -> 0 (goes first)

        coarse = self.rng.random((max(2, h // 24), max(2, w // 24))).astype(np.float32)
        fine = self.rng.random((max(2, h // 4), max(2, w // 4))).astype(np.float32)
        noise = 0.7 * cv2.resize(coarse, (w, h), interpolation=cv2.INTER_CUBIC) + 0.3 * cv2.resize(
            fine, (w, h), interpolation=cv2.INTER_LINEAR
        )
        thr = 0.6 * np.clip(grad, 0, 1) + 0.4 * noise
        region = thr[y0 : y1 + 1, x0 : x1 + 1]
        lo, hi = float(region.min()), float(region.max())
        return np.clip((thr - lo) / max(1e-6, hi - lo), 0, 1).astype(np.float32)

    def _start(self, state: State, t: float, mask: np.ndarray) -> None:
        self.state = state
        self._t0 = t
        self._thr = self._threshold_map(mask)
        self._prev_p = -10.0
        self._prev_front = -10.0

    def _phase(self, t: float, duration: float) -> float:
        s = self.settings.edge_softness + self.settings.glow_width
        return (t - self._t0) / max(0.1, duration) * (1 + 2 * s) - s

    def _sample(self, sel: np.ndarray, frame: np.ndarray, budget: int, x0: int, y0: int):
        ys, xs = np.nonzero(sel)
        n = len(xs)
        empty = np.zeros((0, 2), np.float32), np.zeros((0, 3), np.float32)
        if n == 0:
            return empty
        k = min(budget, int(n * self.settings.particle_density + self.rng.random()))
        if k <= 0:
            return empty
        idx = self.rng.choice(n, size=k, replace=False) if k < n else np.arange(n)
        ys, xs = ys[idx] + y0, xs[idx] + x0
        xy = np.stack([xs, ys], axis=1).astype(np.float32)
        xy += self.rng.random(xy.shape, dtype=np.float32)  # sub-pixel jitter
        return xy, frame[ys, xs].astype(np.float32)

    # ------------------------------------------------------------------ render
    def render(self, frame: np.ndarray, person: np.ndarray, background: np.ndarray | None,
               t: float) -> np.ndarray:
        """Composite one output frame.

        frame: uint8 BGR camera image; person: float mask in [0,1];
        background: float32 BGR clean plate (or None); t: monotonic seconds.
        """
        s = self.settings
        dt = 0.0 if self._last_t is None else t - self._last_t
        self._last_t = t
        self.particles.max_particles = s.max_particles

        if self._pending is not None:
            self._start(self._pending, t, person)
            self._pending = None

        if self.state == State.VISIBLE and len(self.particles) == 0:
            return frame

        out = frame.copy()
        h, w = person.shape
        # Feathered cover mask at quarter resolution: the dilation (~16 px) exceeds
        # the blur reach, so it is fully opaque on the silhouette and also hides
        # the segmentation halo.
        sw, sh = max(1, w // 4), max(1, h // 4)
        small = cv2.resize(person, (sw, sh), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(cv2.dilate(small, np.ones((9, 9), np.uint8)), (0, 0), 1.0)
        ys, xs = np.nonzero(small > 0.004)
        if len(xs) and self.state != State.VISIBLE:
            # Only the area around the person needs per-pixel work.
            y0, y1 = max(0, ys.min() * 4 - 4), min(h, ys.max() * 4 + 8)
            x0, x1 = max(0, xs.min() * 4 - 4), min(w, xs.max() * 4 + 8)
            roi = (slice(y0, y1), slice(x0, x1))
            cover = np.clip(cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)[roi], 0, 1)
            if background is None:
                background = cv2.GaussianBlur(frame, (0, 0), 25).astype(np.float32)
            hidden, glow = self._advance(t, frame, person, roi, x0, y0)
            live = frame[roi].astype(np.float32)
            comp = live + (background[roi] - live) * (cover * hidden)[..., None]
            if glow is not None:
                g = 0.8 * (glow * person[roi])[..., None]
                comp += (np.asarray(s.glow_bgr, np.float32) + 75 - comp) * g
            out[roi] = np.clip(comp, 0, 255).astype(np.uint8)
        elif self.state != State.VISIBLE:
            # Nobody in frame: still let a running transition finish on schedule.
            self._advance(t, frame, person, (slice(0, 0), slice(0, 0)), 0, 0)

        self.particles.update(dt, s.wind_vector, s.particle_speed)
        self.particles.render(out, s.glow_bgr, s.particle_size)
        return out

    def _advance(self, t, frame, person, roi, x0, y0):
        """Step the transition; return (hidden fraction, glow) maps for ``roi``."""
        s = self.settings
        soft = max(1e-3, s.edge_softness)
        gw = max(1e-3, s.glow_width)
        if self.state == State.HIDDEN:
            return np.ones(person[roi].shape, np.float32), None

        thr = self._thr[roi]
        solid = person[roi] > s.segmentation_threshold
        budget = max(0, s.max_particles - len(self.particles))
        if self.state == State.DISSOLVING:
            p = self._phase(t, s.dissolve_duration)
            vis = np.clip((thr - p) / soft, 0, 1)
            glow = np.clip(1 - (thr - p) / gw, 0, 1) * vis
            newly = solid & (thr > self._prev_p) & (thr <= p)
            xy, col = self._sample(newly, frame, budget, x0, y0)
            self.particles.emit_outbound(xy, col, s.wind_vector, s.particle_speed)
            done_state = State.HIDDEN
        else:  # ASSEMBLING
            # Particles take ``travel`` seconds to fly in, so they launch on a front
            # that leads the reveal front by exactly that long.
            travel = 0.4 * s.assemble_duration
            reveal = s.assemble_duration - travel
            p = self._phase(t - travel, reveal)
            front = self._phase(t, reveal)
            vis = np.clip((p - thr) / soft, 0, 1)
            glow = np.clip(1 - (p - thr) / gw, 0, 1) * vis
            newly = solid & (thr > self._prev_front) & (thr <= front)
            xy, col = self._sample(newly, frame, budget, x0, y0)
            self.particles.emit_inbound(xy, col, s.wind_vector, travel)
            self._prev_front = front
            done_state = State.VISIBLE
        self._prev_p = p
        if p >= 1 + soft + s.glow_width:
            self.state = done_state
            if done_state == State.HIDDEN:
                return np.ones(vis.shape, np.float32), None
        return 1 - vis, glow
