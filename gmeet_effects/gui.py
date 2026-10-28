"""Tkinter control panel with live preview."""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

import cv2
from PIL import Image, ImageTk

from .camera import list_cameras
from .config import WIND_DIRECTIONS, Settings
from .pipeline import Pipeline

PREVIEW_W = 800


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = Settings.load()
        self.pipeline = Pipeline(self.settings)
        self._photo = None

        root.title("Snap Vanish - Virtual Camera for Google Meet")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<space>", lambda _e: self.pipeline.trigger())

        main = ttk.Frame(root, padding=8)
        main.pack(fill="both", expand=True)
        self.preview = tk.Label(main, bg="black", width=PREVIEW_W, height=450)
        self.preview.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        side = ttk.Frame(main, padding=(10, 0))
        side.grid(row=0, column=1, sticky="ns")
        self._build_controls(side)

        self.status = tk.StringVar(value="Idle")
        ttk.Label(main, textvariable=self.status, anchor="w").grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._tick()

    # ------------------------------------------------------------------ layout
    def _build_controls(self, side: ttk.Frame) -> None:
        s = self.settings

        run = ttk.LabelFrame(side, text="Camera", padding=6)
        run.pack(fill="x", pady=4)
        ttk.Label(run, text="Webcam").grid(row=0, column=0, sticky="w")
        self.cam_var = tk.StringVar(value=str(s.camera_index))
        self.cam_box = ttk.Combobox(run, textvariable=self.cam_var, width=6,
                                    values=[str(s.camera_index)])
        self.cam_box.grid(row=0, column=1, sticky="w")
        ttk.Button(run, text="Scan", command=self._scan).grid(row=0, column=2, padx=2)
        ttk.Label(run, text="Resolution").grid(row=1, column=0, sticky="w")
        self.res_var = tk.StringVar(value=f"{s.width}x{s.height}")
        ttk.Combobox(run, textvariable=self.res_var, width=10, state="readonly",
                     values=["640x360", "960x540", "1280x720"]).grid(row=1, column=1, columnspan=2,
                                                                       sticky="w")
        self.vcam_var = tk.BooleanVar(value=s.vcam_enabled)
        ttk.Checkbutton(run, text="Send to virtual camera", variable=self.vcam_var).grid(
            row=2, column=0, columnspan=3, sticky="w")
        self.start_btn = ttk.Button(run, text="Start", command=self.toggle_run)
        self.start_btn.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        bg = ttk.LabelFrame(side, text="Background", padding=6)
        bg.pack(fill="x", pady=4)
        ttk.Button(bg, text="Capture clean background (3 s)",
                   command=self.pipeline.capture_background).pack(fill="x")
        ttk.Button(bg, text="Clear background", command=self.pipeline.clear_background).pack(
            fill="x", pady=(2, 0))
        self._check(bg, "Adapt to lighting changes", "adaptive_background")

        fx = ttk.LabelFrame(side, text="Effect", padding=6)
        fx.pack(fill="x", pady=4)
        self._scale(fx, "Vanish duration (s)", "dissolve_duration", 0.8, 6.0)
        self._scale(fx, "Reappear duration (s)", "assemble_duration", 0.8, 6.0)
        self._scale(fx, "Particle density", "particle_density", 0.05, 1.0)
        self._scale(fx, "Particle speed", "particle_speed", 0.3, 3.0)
        self._scale(fx, "Particle size", "particle_size", 1, 4, integer=True)
        self._scale(fx, "Glow width", "glow_width", 0.0, 0.2)
        row = ttk.Frame(fx)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Wind").pack(side="left")
        wind = tk.StringVar(value=s.wind_direction)
        cb = ttk.Combobox(row, textvariable=wind, values=list(WIND_DIRECTIONS), width=9,
                          state="readonly")
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda _e: setattr(s, "wind_direction", wind.get()))
        self.color_btn = tk.Button(row, text="Glow colour", width=10, command=self._pick_color)
        self.color_btn.pack(side="right")
        self._paint_color()

        det = ttk.LabelFrame(side, text="Snap detection", padding=6)
        det.pack(fill="x", pady=4)
        self._check(det, "Trigger on finger snap", "snap_enabled")
        self._scale(det, "Sensitivity", "snap_sensitivity", 0.5, 2.0)
        self._scale(det, "Cooldown (s)", "snap_cooldown", 0.3, 3.0)
        self._check(det, "Show hand landmarks (preview)", "show_landmarks")
        self._check(det, "Mirror preview", "mirror_preview")
        ttk.Button(det, text="Trigger now  [Space]", command=self.pipeline.trigger).pack(
            fill="x", pady=(4, 0))

    def _scale(self, parent, label: str, attr: str, lo: float, hi: float, integer: bool = False):
        frame = ttk.Frame(parent)
        frame.pack(fill="x")
        value = tk.DoubleVar(value=getattr(self.settings, attr))
        text = tk.StringVar()

        def changed(*_):
            v = round(value.get()) if integer else round(value.get(), 2)
            setattr(self.settings, attr, int(v) if integer else v)
            text.set(str(v))

        ttk.Label(frame, text=label).pack(anchor="w")
        ttk.Scale(frame, from_=lo, to=hi, variable=value, command=changed).pack(
            side="left", fill="x", expand=True)
        ttk.Label(frame, textvariable=text, width=5).pack(side="right")
        changed()

    def _check(self, parent, label: str, attr: str) -> None:
        var = tk.BooleanVar(value=getattr(self.settings, attr))
        ttk.Checkbutton(parent, text=label, variable=var,
                        command=lambda: setattr(self.settings, attr, var.get())).pack(anchor="w")

    # ----------------------------------------------------------------- actions
    def _scan(self) -> None:
        cams = list_cameras()
        self.cam_box["values"] = [str(c) for c in cams] or ["0"]
        if cams and int(self.cam_var.get() or 0) not in cams:
            self.cam_var.set(str(cams[0]))

    def _pick_color(self) -> None:
        r, g, b = self.settings.glow_color
        rgb, _ = colorchooser.askcolor(color=f"#{r:02x}{g:02x}{b:02x}", title="Glow colour")
        if rgb:
            self.settings.glow_color = [int(c) for c in rgb]
            self._paint_color()

    def _paint_color(self) -> None:
        r, g, b = self.settings.glow_color
        self.color_btn.configure(bg=f"#{r:02x}{g:02x}{b:02x}")

    def toggle_run(self) -> None:
        if self.pipeline.alive:
            self.pipeline.stop()
            self.start_btn.configure(text="Start")
            return
        try:
            self.settings.camera_index = int(self.cam_var.get())
            w, h = (int(v) for v in self.res_var.get().split("x"))
        except ValueError:
            messagebox.showerror("Invalid setting", "Camera index / resolution is invalid.")
            return
        self.settings.width, self.settings.height = w, h
        self.settings.vcam_enabled = self.vcam_var.get()
        self.pipeline.start()
        self.start_btn.configure(text="Stop")

    def _tick(self) -> None:
        frame = self.pipeline.latest_preview()
        st = self.pipeline.status
        if frame is not None and st.running:
            h, w = frame.shape[:2]
            pw = max(320, self.preview.winfo_width())
            ph = int(h * pw / w)
            img = cv2.cvtColor(cv2.resize(frame, (pw, ph)), cv2.COLOR_BGR2RGB)
            self._photo = ImageTk.PhotoImage(Image.fromarray(img))
            self.preview.configure(image=self._photo)
        if not self.pipeline.alive and self.start_btn["text"] == "Stop":
            self.start_btn.configure(text="Start")
        self.status.set(
            f"{st.message}  |  {st.fps:4.1f} fps  |  effect: {st.state}  |  "
            f"virtual cam: {st.vcam}  |  background: {self.pipeline.status.background}  |  "
            f"snaps: {st.snap_count}")
        self.root.after(15, self._tick)

    def on_close(self) -> None:
        self.pipeline.stop()
        try:
            self.settings.save()
        except OSError:
            pass
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.25)
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
