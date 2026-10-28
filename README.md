# Snap Vanish: a disintegration effect for Google Meet

Snap Vanish is a standalone Windows app. Snap your fingers on camera and you
break up into glowing dust that blows away, leaving the background behind you
visible. Snap again and the particles fly back in and you reappear.

The app shows up as a regular webcam, so Google Meet (or Zoom, Teams, and so
on) picks it up like any other camera, and everyone in the call sees the
effect. OBS is not needed, and nothing leaves your computer: all of the vision
models run locally.

```
Webcam ─► OpenCV capture ─► MediaPipe Hands ──► snap detector ─┐
                       └──► MediaPipe Selfie Segmentation ─────┤
                                                               ▼
           clean background plate ─► disintegration effect (NumPy particles)
                                                               │
                         Tk preview ◄──────────────────────────┤
                                                               ▼
                     pyvirtualcam ─► Unity Capture driver ─► Google Meet
```

## Requirements

* Windows 10 or 11, 64-bit
* Python 3.10 – 3.12 (64-bit). MediaPipe 0.10.21 has no wheels for 3.13.
* The **Unity Capture** virtual camera driver

## Setup

1. **Install the Unity Capture driver.** Download
   <https://github.com/schellingb/UnityCapture> (Code → Download ZIP), extract
   it, open the `Install` folder and run `Install.bat` **as administrator**.
   This registers a DirectShow camera named **"Unity Video Capture"**.
   (To remove it later, run `Uninstall.bat`.)
2. **Install the Python dependencies:**

   ```bash
   py -3.12 -m venv .venv
   ```

   ```bash
   .venv\Scripts\activate
   ```

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the app:**

   ```bash
   python main.py
   ```

   Or just double-click `run.bat`, which creates the venv on first run.

## Using it in Google Meet

1. In Snap Vanish, pick your webcam (use **Scan** if you have several cameras)
   and press **Start**. The status bar should show `virtual cam: Unity Video Capture`.
2. Press **Capture clean background (3 s)**, then step out of the frame
   before the countdown ends. The app records a clean background (the median
   of 20 frames) and saves it, so you only have to do this again if the room
   or the camera position changes.
3. In Google Meet, go to **Settings → Video → Camera** and choose
   **Unity Video Capture**. Do this after pressing Start. If Meet was already
   open, refresh the tab.
4. Snap your fingers to vanish, and snap again to reappear. **Space** or the
   **Trigger now** button does the same thing.

> Start Snap Vanish *before* selecting the camera in Meet. Your physical webcam
> can only be opened by one program at a time, so Meet must use the virtual
> camera and never the real one.

### Snapping tips

* Keep the snapping hand clearly visible, palm roughly facing the camera, and
  not too close to the frame edge.
* Turn on **Show hand landmarks** to check tracking. The thumb tip and the
  middle fingertip are drawn in yellow.
* If snaps are missed, raise **Sensitivity**. If it triggers by accident, lower
  it or increase **Cooldown**.

## Settings

| Control | Effect |
|---|---|
| Vanish / Reappear duration | Length of each animation |
| Particle density | Fraction of your pixels that become particles |
| Particle speed / size | How fast the dust drifts and how big each grain is |
| Glow width / colour | The burning-ember edge that leads the dissolve |
| Wind | Direction the dust blows. The downwind side dissolves first. |
| Adapt to lighting changes | Keeps refreshing the background plate from visible background pixels |
| Mirror preview | Mirrors only the local preview. Meet receives the true (unmirrored) image. |

Settings are saved to `%USERPROFILE%\.gmeet_effects\settings.json`, and the
background plate to `background.png` in the same folder.

## How it works

* **Snap detection** (`gmeet_effects/gestures.py`): for each hand, the detector
  tracks the thumb-tip↔middle-tip gap and the middle-tip↔wrist reach, both
  measured in palm lengths. A snap is a pinch (small gap) followed within
  350 ms by a release (large gap) *and* the middle finger curling toward the
  palm. That last condition is what keeps simply opening your hand from
  counting as a snap.
* **Segmentation** (`vision.py`): MediaPipe Selfie Segmentation (landscape
  model), temporally smoothed to reduce flicker.
* **Effect** (`effect.py`): when a transition starts, every pixel gets a
  dissolve time from a directional gradient along the wind plus multi-scale
  noise. As the front sweeps across you, pixels fade to the clean background
  with a glowing edge. Some of the dissolved pixels are spawned as particles,
  which carry their colour, drift with wind and turbulence, and cool from
  ember to their own colour as they fade. To reappear, particles launch from
  downwind ahead of the reveal front, fly back on eased, swirling paths, and
  land just as their pixel reappears.
* **Background** (`background.py`): the captured plate fills the area your
  body covered, and the rest of the frame stays live. Without a captured
  plate, the app learns the background from areas you uncover and inpaints
  any area it has never seen.
* **Performance**: per-pixel work is limited to the area around you, and the
  particles are vectorised NumPy plus OpenCV blending. That comes to about
  20 ms per 720p frame on top of the MediaPipe inference. If your PC
  struggles, choose 960x540.

## Building a standalone .exe

```bash
build_exe.bat
```

This produces `dist\SnapVanish\SnapVanish.exe`, which runs without Python
installed. The Unity Capture driver still has to be installed separately on
each machine.

## Troubleshooting

* **`virtual cam: error ...`**: the Unity Capture driver isn't installed, or
  `Install.bat` wasn't run as administrator. Turning off **Send to virtual
  camera** lets you still use the preview.
* **Meet shows "Unity Video Capture" with a "please start sending" image**:
  press Start in Snap Vanish, then reselect the camera in Meet.
* **"Could not open webcam"**: another app (or Meet itself) is using the real
  camera. Close it, or pick a different index.
* **Ghosting where you were standing**: capture the background again under the
  current lighting.

## Development

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest
```

The tests cover snap detection, the effect state machine and compositing, and
the particle system. They don't need a webcam or MediaPipe.
