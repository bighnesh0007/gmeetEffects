"""Entry point (also used by PyInstaller).

``SnapVanish.exe --self-test`` loads the MediaPipe models on a blank frame and
exits with code 0 on success; CI uses it to verify the packaged build.
"""

import sys


def self_test() -> int:
    import numpy as np

    from gmeet_effects.vision import HandTracker, PersonSegmenter

    frame = np.zeros((720, 1280, 3), np.uint8)
    hands, seg = HandTracker(), PersonSegmenter()
    hands.process(frame)
    mask = seg.process(frame)
    hands.close()
    seg.close()
    return 0 if mask.shape == (720, 1280) else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    from gmeet_effects.gui import main

    main()
