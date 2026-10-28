"""Processing thread: camera -> hands/segmentation -> effect -> virtual camera."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

from .background import BackgroundModel
from .camera import Camera
from .config import BACKGROUND_PATH, Settings
from .effect import DisintegrationEffect, State
from .gestures import SnapDetector, SnapParams


@dataclass
class Status:
    running: bool = False
    fps: float = 0.0
    state: str = State.VISIBLE.value
    vcam: str = "off"
    browser: str = "off"
    background: str = "none"
    message: str = ""
    snap_count: int = 0


class Pipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.background = BackgroundModel()
        self.background.load(BACKGROUND_PATH)
        self.effect = DisintegrationEffect(settings)
        self.status = Status(background="saved plate" if self.background.captured else "none")
        self._preview: np.ndarray | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._trigger = threading.Event()
        self._capture_request: tuple[float, int] | None = None
        self._capture_frames: list[np.ndarray] = []

    # ----------------------------------------------------------------- control
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="pipeline", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def trigger(self) -> None:
        self._trigger.set()

    def capture_background(self, delay: float = 3.0, frames: int = 20) -> None:
        """Grab a clean plate after ``delay`` seconds (time to step out of frame)."""
        self._capture_frames = []
        self._capture_request = (time.monotonic() + delay, frames)

    def clear_background(self) -> None:
        self.background.reset()
        try:
            BACKGROUND_PATH.unlink()
        except OSError:
            pass
        self.status.background = "none (auto-learning)"

    def latest_preview(self) -> np.ndarray | None:
        with self._lock:
            return self._preview

    # -------------------------------------------------------------------- loop
    def _run(self) -> None:
        s = self.settings
        cam = vcam = hands = seg = server = None
        try:
            if s.browser_enabled:
                from .stream_server import FrameServer

                try:
                    server = FrameServer(s.browser_port)
                    server.start()
                    self.status.browser = "waiting for Meet"
                except OSError as exc:  # port already in use, ...
                    server = None
                    self.status.browser = f"error: {exc}"
            self.status.message = "Opening webcam..."
            cam = Camera(s.camera_index, s.width, s.height, s.fps)
            self.status.message = "Loading MediaPipe models..."
            from .vision import HandTracker, PersonSegmenter, draw_hands

            hands = HandTracker()
            seg = PersonSegmenter()
            if s.vcam_enabled:
                try:
                    from .virtualcam import VirtualCamera

                    vcam = VirtualCamera(s.width, s.height, s.fps, s.vcam_backend, s.vcam_device)
                    self.status.vcam = vcam.device
                except Exception as exc:  # driver missing, device busy, ...
                    self.status.vcam = f"error: {exc}"
            snap = SnapDetector(aspect=s.width / s.height)
            self.status.running = True
            self.status.message = "Running"
            seq = 0
            times: deque[float] = deque(maxlen=30)

            while not self._stop.is_set():
                seq, frame = cam.read(seq)
                if frame is None:
                    continue
                t = time.monotonic()
                if frame.shape[1] != s.width or frame.shape[0] != s.height:
                    frame = cv2.resize(frame, (s.width, s.height))
                if s.flip_output:
                    frame = cv2.flip(frame, 1)

                detected = hands.process(frame) if s.snap_enabled or s.show_landmarks else []
                snap.params = SnapParams(cooldown=s.snap_cooldown, sensitivity=s.snap_sensitivity)
                snapped = s.snap_enabled and snap.update(t, detected)
                if snapped or self._trigger.is_set():
                    self._trigger.clear()
                    self.effect.toggle()
                    self.status.snap_count += snapped

                person = seg.process(frame)
                self._handle_capture(frame, t)
                self.background.update(frame, person, s.adaptive_background)

                out = self.effect.render(frame, person, self.background.get(), t)
                if vcam is not None:
                    vcam.send(out)
                if server is not None:
                    if server.active:
                        ok, jpeg = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        if ok:
                            server.publish(jpeg.tobytes())
                        self.status.browser = "streaming to Meet"
                    else:
                        self.status.browser = "waiting for Meet"

                preview = out.copy() if s.show_landmarks else out
                if s.show_landmarks:
                    draw_hands(preview, detected)
                if self._capture_request:
                    left = self._capture_request[0] - t
                    text = f"Step out of frame: {left:.1f}s" if left > 0 else "Capturing..."
                    cv2.putText(preview, text, (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.4,
                                (0, 220, 255), 3, cv2.LINE_AA)
                if s.mirror_preview:
                    preview = cv2.flip(preview, 1)
                with self._lock:
                    self._preview = preview

                times.append(t)
                if len(times) > 1:
                    self.status.fps = (len(times) - 1) / max(1e-6, times[-1] - times[0])
                self.status.state = self.effect.state.value
        except Exception as exc:
            self.status.message = f"Error: {exc}"
        finally:
            self.status.running = False
            for obj, close in ((server, "stop"), (vcam, "close"), (hands, "close"), (seg, "close"),
                               (cam, "release")):
                if obj is not None:
                    try:
                        getattr(obj, close)()
                    except Exception:
                        pass
            self.status.vcam = "off"
            self.status.browser = "off"
            if not self.status.message.startswith("Error"):
                self.status.message = "Stopped"

    def _handle_capture(self, frame: np.ndarray, t: float) -> None:
        if not self._capture_request or t < self._capture_request[0]:
            return
        self._capture_frames.append(frame.copy())
        if len(self._capture_frames) >= self._capture_request[1]:
            self.background.capture(self._capture_frames)
            self.background.save(BACKGROUND_PATH)
            self._capture_frames = []
            self._capture_request = None
            self.effect.reset()
            self.status.background = "captured"
