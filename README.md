# Snap Vanish: a disintegration effect for Google Meet

Snap Vanish is a standalone Windows app. Snap your fingers on camera and you
break up into glowing dust that blows away, leaving the background behind you
visible. Snap again and the particles fly back in and you reappear.

The app works **without administrator rights and without installing anything**.
It ships as a portable folder (unzip and run), and Google Meet receives the
video through a small browser extension. Extensions can be loaded without
admin rights. OBS and virtual-camera drivers are not needed, and nothing
leaves your computer: all of the vision models run locally, and the app only
listens on `127.0.0.1`.

```
Webcam ─► OpenCV capture ─► MediaPipe Hands ──► snap detector ─┐
                       └──► MediaPipe Selfie Segmentation ─────┤
                                                               ▼
           clean background plate ─► disintegration effect (NumPy particles)
                                                               │
               Tk preview ◄────────────────────────────────────┤
                                                               ▼
   local frame server (127.0.0.1:8765) ─► browser extension ─► "Snap Vanish Camera" in Meet
```

## Getting the app (no installs)

1. On GitHub, open this repository's **Actions** tab, then **Build portable Windows app**.
2. Open the latest green run and download the **SnapVanish-windows** artifact (a zip).
   Tagged releases (`v*`) also attach the zip under **Releases**.
3. Unzip it anywhere you can write to, for example `Documents\SnapVanish`.
   It includes Python, OpenCV, MediaPipe and everything else, so nothing gets
   installed on your system.

Then follow `QUICKSTART.txt` in that folder:

1. **Run `SnapVanish.exe`.** If SmartScreen warns you, click *More info* → *Run anyway*.
2. **Load the extension once.** Open `chrome://extensions` (or `edge://extensions`),
   turn on **Developer mode**, click **Load unpacked** and pick the
   `browser_extension` folder.
3. In Snap Vanish, choose your webcam and press **Start**. Then press
   **Capture clean background (3 s)** and step out of the frame. The app
   saves the background, so you only redo this if the room or the camera
   position changes.
4. In Google Meet (reload the tab if it was open), go to **Settings → Video → Camera**
   and choose **Snap Vanish Camera**.
5. Snap to vanish, and snap again to reappear. **Space** or the **Trigger now**
   button does the same thing.

**Open output test page** in the app shows exactly what Meet receives.

> Snap Vanish uses your real webcam, so Meet must use **Snap Vanish Camera**
> and never the physical camera. When no camera is specifically chosen, the
> extension makes Snap Vanish the default.

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
| Browser camera for Meet | Serves frames to the extension (default, no install) |
| Virtual camera driver | Optional. Sends frames to Unity Capture instead, for desktop apps like Zoom or Teams. The driver needs admin to install. |

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
* **Delivery to Meet** (`stream_server.py`, `browser_extension/`): the app
  JPEG-encodes each frame only while the extension is fetching. The
  extension's service worker long-polls `127.0.0.1:8765`, and a script on
  meet.google.com draws the frames onto a canvas and returns its
  `captureStream()` as the camera. Your microphone is passed through
  untouched.

## Troubleshooting

* **Meet doesn't list "Snap Vanish Camera"**: check that the extension is enabled
  on `chrome://extensions`, then reload the Meet tab.
* **Meet shows "Waiting for the Snap Vanish app"**: press Start in the app.
  The status bar should change to `Meet: streaming to Meet`.
* **"Developer mode" is greyed out**: your organisation has blocked unpacked
  extensions by policy. Use the virtual-camera option on a machine where you
  have admin rights, or ask IT to allow the extension.
* **"Could not open webcam"**: another app is using the real camera. Close it
  (or set Meet to Snap Vanish Camera), or pick a different index and press **Scan**.
* **`Meet: error ... address already in use`**: another copy of Snap Vanish is
  already running.
* **Ghosting where you were standing**: capture the background again under the
  current lighting.
* **Slow on an older laptop**: choose 960x540.

## Running from source / building yourself (optional)

If you can run Python (the per-user installer from python.org doesn't need
admin), you can run from source instead. All packages install into your user
folder or a venv:

```bash
pip install --user -r requirements.txt
```

```bash
python main.py
```

`build_exe.bat` builds the same portable folder locally.

## Development

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest
```

The tests cover snap detection, the effect state machine and compositing, the
particle system, and the local frame server. They don't need a webcam or MediaPipe.
