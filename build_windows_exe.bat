@echo off
REM ---------------------------------------------------------------------------
REM Build Diamond Scorer into a single Windows .exe using PyInstaller.
REM Double-click this file, or run it from the project root. The window stays
REM open at the end so you can read the result. This produces an .exe matching
REM your Python's architecture (use build_windows_exe_32bit.bat for a 32-bit
REM build that also runs on 32-bit Windows).
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

echo [1/3] Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt pyinstaller
if errorlevel 1 (
  echo.
  echo ERROR: Dependency installation failed. See the messages above.
  pause
  goto :end
)

echo [2/3] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] Building executable...
pyinstaller --noconfirm --clean --windowed --name DiamondScorer ^
  --add-data "frontend;frontend" ^
  --collect-all webview ^
  --collect-all reportlab ^
  main.py
if errorlevel 1 (
  echo.
  echo ERROR: PyInstaller build failed. See the messages above.
  pause
  goto :end
)

echo.
echo Done. The executable is in the dist\DiamondScorer folder.
echo.
pause

:end
endlocal
