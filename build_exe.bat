@echo off
REM Optional: build the portable app yourself (needs Python 3.12; no admin required).
REM Most users can download the prebuilt zip from GitHub Actions instead.
pip install --user -r requirements-dev.txt || exit /b 1
python -m PyInstaller --noconfirm --windowed --name SnapVanish ^
  --collect-data mediapipe --collect-binaries mediapipe ^
  --collect-all pyvirtualcam ^
  main.py || exit /b 1
xcopy /E /I /Y browser_extension dist\SnapVanish\browser_extension >nul
copy /Y QUICKSTART.txt dist\SnapVanish\ >nul
echo.
echo Done: dist\SnapVanish\SnapVanish.exe
