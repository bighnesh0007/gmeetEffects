import numpy as np

from gmeet_effects.config import Settings
from gmeet_effects.effect import DisintegrationEffect, State
from gmeet_effects.particles import ParticleSystem


def scene(h=120, w=160):
    frame = np.full((h, w, 3), 50, np.uint8)
    frame[30:110, 60:100] = (0, 0, 255)  # "person" is red
    mask = np.zeros((h, w), np.float32)
    mask[30:110, 60:100] = 1.0
    bg = np.full((h, w, 3), 50, np.float32)
    return frame, mask, bg


def run_until(effect, state, frame, mask, bg, t, dt=1 / 30, limit=10.0):
    out = None
    while t < limit:
        out = effect.render(frame, mask, bg, t)
        t += dt
        if effect.state == state and len(effect.particles) == 0:
            break
    return out, t


def test_full_cycle_vanish_and_reappear():
    s = Settings(dissolve_duration=1.0, assemble_duration=1.0, particle_density=0.5)
    fx = DisintegrationEffect(s, seed=1)
    frame, mask, bg = scene()

    assert fx.render(frame, mask, bg, 0.0) is frame  # visible passthrough
    fx.toggle()
    out = fx.render(frame, mask, bg, 0.0)
    assert fx.state == State.DISSOLVING

    out, t = run_until(fx, State.HIDDEN, frame, mask, bg, 0.05)
    assert fx.state == State.HIDDEN
    assert np.abs(out.astype(int) - 50).max() <= 1  # person fully replaced by background

    fx.toggle()
    out, t = run_until(fx, State.VISIBLE, frame, mask, bg, t)
    assert fx.state == State.VISIBLE
    assert (out[50, 80] == (0, 0, 255)).all()


def test_dissolve_emits_particles():
    s = Settings(dissolve_duration=1.0, particle_density=1.0)
    fx = DisintegrationEffect(s, seed=2)
    frame, mask, bg = scene()
    fx.toggle()
    for i in range(10):
        fx.render(frame, mask, bg, i / 30)
    assert len(fx.particles) > 0


def test_toggle_ignored_mid_transition():
    fx = DisintegrationEffect(Settings(), seed=3)
    frame, mask, bg = scene()
    fx.toggle()
    fx.render(frame, mask, bg, 0.0)
    fx.toggle()
    fx.render(frame, mask, bg, 0.1)
    assert fx.state == State.DISSOLVING


def test_particle_cap_and_expiry():
    ps = ParticleSystem(max_particles=100, seed=0)
    xy = np.random.rand(500, 2).astype(np.float32) * 50
    ps.emit_outbound(xy, np.zeros((500, 3)), (1, 0))
    assert len(ps) == 100
    for _ in range(40):
        ps.update(0.1, (1, 0))
    assert len(ps) == 0
