"""User settings, persisted as JSON in the user's home directory."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_DIR = Path(os.environ.get("GMEET_EFFECTS_HOME", Path.home() / ".gmeet_effects"))
SETTINGS_PATH = APP_DIR / "settings.json"
BACKGROUND_PATH = APP_DIR / "background.png"

WIND_DIRECTIONS = {
    "right": (1.0, 0.0),
    "left": (-1.0, 0.0),
    "up": (0.0, -1.0),
    "up-right": (0.7071, -0.7071),
    "up-left": (-0.7071, -0.7071),
}


@dataclass
class Settings:
    # Capture / output
    camera_index: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 30
    browser_enabled: bool = True  # serve frames to the browser extension (no install needed)
    browser_port: int = 8765
    vcam_enabled: bool = False  # optional virtual-camera driver output (needs admin to install)
    vcam_backend: str = "unitycapture"  # "unitycapture", "obs", or "auto"
    vcam_device: str = ""  # empty = backend default ("Unity Video Capture")
    mirror_preview: bool = True
    flip_output: bool = False

    # Effect
    dissolve_duration: float = 2.5
    assemble_duration: float = 2.0
    particle_density: float = 0.35  # fraction of dissolving pixels that become particles
    particle_size: int = 2
    particle_speed: float = 1.0
    max_particles: int = 60000
    wind_direction: str = "right"
    glow_color: list = field(default_factory=lambda: [255, 140, 40])  # RGB
    glow_width: float = 0.06
    edge_softness: float = 0.03

    # Detection
    snap_enabled: bool = True
    snap_sensitivity: float = 1.0
    snap_cooldown: float = 1.2
    segmentation_threshold: float = 0.5
    adaptive_background: bool = True
    show_landmarks: bool = False

    @property
    def wind_vector(self) -> tuple[float, float]:
        return WIND_DIRECTIONS.get(self.wind_direction, WIND_DIRECTIONS["right"])

    @property
    def glow_bgr(self) -> tuple[int, int, int]:
        r, g, b = self.glow_color
        return int(b), int(g), int(r)

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> "Settings":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path = SETTINGS_PATH) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
