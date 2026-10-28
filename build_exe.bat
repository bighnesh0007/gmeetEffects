@echo off
REM Builds a standalone dist\SnapVanish\SnapVanish.exe (run from an activated venv).
pip install -r requirements-dev.txt || exit /b 1
pyinstaller --noconfirm --windowed --name SnapVanish ^
  --collect-data mediapipe --collect-binaries mediapipe ^
  --collect-all pyvirtualcam ^
  main.py
echo.
echo Done: dist\SnapVanish\SnapVanish.exe
