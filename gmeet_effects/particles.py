"""Vectorised NumPy particle system for the dust / ember effect."""

from __future__ import annotations

import cv2
import numpy as np


class ParticleSystem:
    """Particles are stored in flat arrays; inactive slots are compacted away.

    Two kinds of particles exist:
    * *outbound* (``inbound == False``): spawned from dissolving pixels, they
      drift away on the wind with turbulence and fade out.
    * *inbound*: spawned for reappearing pixels, they fly from a scattered start
      position back to their target pixel, arriving exactly as it appears.
    """

    def __init__(self, max_particles: int = 60000, seed: int | None = None):
        self.max_particles = max_particles
        self.rng = np.random.default_rng(seed)
        self._alloc(0)

    def _alloc(self, n: int) -> None:
        self.pos = np.zeros((n, 2), np.float32)
        self.vel = np.zeros((n, 2), np.float32)
        self.start = np.zeros((n, 2), np.float32)
        self.target = np.zeros((n, 2), np.float32)
        self.color = np.zeros((n, 3), np.float32)
        self.age = np.zeros(n, np.float32)
        self.life = np.ones(n, np.float32)
        self.inbound = np.zeros(n, bool)

    def __len__(self) -> int:
        return len(self.age)

    def clear(self) -> None:
        self._alloc(0)

    def _append(self, **arrays) -> None:
        room = self.max_particles - len(self)
        if room <= 0:
            return
        n = min(room, len(arrays["pos"]))
        for name, value in arrays.items():
            setattr(self, name, np.concatenate([getattr(self, name), value[:n]]))

    def emit_outbound(self, xy: np.ndarray, colors: np.ndarray, wind, speed: float = 1.0) -> None:
        n = len(xy)
        if n == 0:
            return
        r = self.rng
        wind = np.asarray(wind, np.float32)
        base = r.uniform(30, 140, (n, 1)).astype(np.float32) * speed
        vel = wind * base + r.normal(0, 25 * speed, (n, 2)).astype(np.float32)
        vel[:, 1] -= r.uniform(5, 40, n).astype(np.float32) * speed  # dust rises a little
        xy = xy.astype(np.float32)
        self._append(
            pos=xy.copy(), vel=vel, start=xy.copy(), target=xy.copy(),
            color=colors.astype(np.float32),
            age=np.zeros(n, np.float32),
            life=r.uniform(0.9, 2.2, n).astype(np.float32),
            inbound=np.zeros(n, bool),
        )

    def emit_inbound(self, xy: np.ndarray, colors: np.ndarray, wind, travel_time: float) -> None:
        n = len(xy)
        if n == 0:
            return
        r = self.rng
        wind = np.asarray(wind, np.float32)
        dist = r.uniform(60, 320, (n, 1)).astype(np.float32)
        start = xy + wind * dist + r.normal(0, 40, (n, 2)).astype(np.float32)
        start[:, 1] -= r.uniform(0, 60, n).astype(np.float32)
        life = (travel_time * r.uniform(0.85, 1.0, n)).astype(np.float32)
        self._append(
            pos=start.copy(), vel=np.zeros((n, 2), np.float32),
            start=start, target=xy.astype(np.float32),
            color=colors.astype(np.float32),
            age=np.zeros(n, np.float32), life=life, inbound=np.ones(n, bool),
        )

    def update(self, dt: float, wind, speed: float = 1.0) -> None:
        if len(self) == 0:
            return
        dt = np.float32(min(dt, 0.1))
        self.age += dt
        alive = self.age < self.life
        if not alive.all():
            for name in ("pos", "vel", "start", "target", "color", "age", "life", "inbound"):
                setattr(self, name, getattr(self, name)[alive])
        n = len(self)
        if n == 0:
            return
        # Outbound physics runs on every slot (cheaper than masked indexing);
        # inbound slots are then overwritten with their interpolated path.
        self.vel += np.asarray(wind, np.float32) * (90 * speed * dt)
        self.vel += self.rng.standard_normal((n, 2), dtype=np.float32) * (120 * speed * dt)
        self.vel *= np.float32(0.985)
        self.pos += self.vel * dt
        if self.inbound.any():
            inn = np.flatnonzero(self.inbound)
            u = np.clip(self.age[inn] / self.life[inn], 0, 1)[:, None]
            ease = 1 - (1 - u) ** 3  # ease-out cubic
            # Slight swirl perpendicular to the path that vanishes on arrival.
            path = self.target[inn] - self.start[inn]
            perp = np.stack([-path[:, 1], path[:, 0]], axis=1) * 0.15
            self.pos[inn] = self.start[inn] + path * ease + perp * np.sin(np.pi * u)

    def render(self, img: np.ndarray, glow_bgr, size: int = 2) -> None:
        """Blend particles into the uint8 BGR image in place.

        Particles are splatted into a colour/alpha layer (one pixel each), grown to
        ``size`` with a max filter, then blended over the touched region only.
        """
        if len(self) == 0:
            return
        h, w = img.shape[:2]
        ix = self.pos[:, 0].astype(np.int32)
        iy = self.pos[:, 1].astype(np.int32)
        ok = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
        if not ok.any():
            return
        ix, iy = ix[ok], iy[ok]
        u = np.clip(self.age[ok] / self.life[ok], 0, 1)
        inbound = self.inbound[ok]
        alpha = np.where(inbound, 0.35 + 0.65 * u, (1 - u) ** 1.5)
        # Outbound particles start hot (ember colour) and cool to their pixel colour;
        # inbound ones glow while travelling and settle to the true colour.
        heat = np.where(inbound, 0.8 * (1 - u), np.clip(1 - u * 3, 0, 1) * 0.7)[:, None]
        col = self.color[ok] * (1 - heat) + np.asarray(glow_bgr, np.float32) * heat

        pad = max(0, size - 1)
        x0, x1 = ix.min(), min(w, ix.max() + 1 + pad)
        y0, y1 = iy.min(), min(h, iy.max() + 1 + pad)
        lh, lw = y1 - y0, x1 - x0
        layer = np.zeros((lh, lw, 3), np.float32)
        a = np.zeros((lh, lw), np.float32)
        layer[iy - y0, ix - x0] = col
        a[iy - y0, ix - x0] = alpha
        if size > 1:
            k = np.ones((size, size), np.uint8)
            anchor = (0, 0)  # grow right/down, matching the pixel origin
            layer = cv2.dilate(layer, k, anchor=anchor)
            a = cv2.dilate(a, k, anchor=anchor)
        roi = img[y0:y1, x0:x1]
        base = roi.astype(np.float32)
        roi[:] = np.clip(base + (layer - base) * a[..., None], 0, 255).astype(np.uint8)
