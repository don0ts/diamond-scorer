@echo off
REM ---------------------------------------------------------------------------
REM Build Diamond Scorer into a 32-bit (x86) Windows .exe using PyInstaller.
REM
REM A 32-bit executable runs on BOTH 32-bit and 64-bit Windows, so this is the
REM most broadly compatible build. The catch: PyInstaller always produces an
REM .exe that matches the architecture of the Python interpreter running it,
REM so this script must run under a 32-bit (x86) Python.
REM
REM Just double-click this file. It will automatically locate a 32-bit Python
REM (preferring the "py -3-32" launcher) and refuse to continue if only a
REM 64-bit interpreter is available. The window stays open at the end so you
REM can read the result.
REM
REM How to get 32-bit Python if you don't have one:
REM   1. https://www.python.org/downloads/windows/
REM   2. Download the "Windows installer (32-bit)" for Python 3.11 or 3.12.
REM   3. Install it (ticking "py launcher" is enough; PATH is not required).
REM   4. Double-click this script again.
REM ---------------------------------------------------------------------------
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo [1/4] Locating a 32-bit Python interpreter...
set "PYEXE="

REM Prefer the Python launcher's explicit 32-bit build.
py -3-32 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3-32"

REM Otherwise accept "python" on PATH only if it is itself 32-bit.
if not defined PYEXE (
  python -c "import struct,sys; sys.exit(0 if struct.calcsize('P')*8==32 else 1)" >nul 2>&1
  if not errorlevel 1 set "PYEXE=python"
)

if not defined PYEXE (
  echo.
  echo ERROR: Could not find a 32-bit Python.
  echo.
  echo   - "py -3-32" is not available, and
  echo   - the "python" on your PATH is 64-bit ^(or missing^).
  echo.
  echo   A 64-bit Python can only build a 64-bit .exe, which will NOT run on
  echo   32-bit Windows. Please install 32-bit Python ^(see the notes at the
  echo   top of this file^) and run this script again.
  echo.
  pause
  goto :end
)

for /f "delims=" %%v in ('%PYEXE% -c "import struct;print(struct.calcsize('P')*8)"') do set "BITS=%%v"
echo       Using: %PYEXE%  (%BITS%-bit)

echo [2/4] Installing dependencies...
%PYEXE% -m pip install --upgrade pip
%PYEXE% -m pip install -r requirements-desktop.txt pyinstaller
if errorlevel 1 (
  echo.
  echo ERROR: Dependency installation failed. See the messages above.
  pause
  goto :end
)

echo [3/4] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/4] Building 32-bit executable...
%PYEXE% -m PyInstaller --noconfirm --clean --windowed --name DiamondScorer32 ^
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
echo Done. The 32-bit executable is in the dist\DiamondScorer32 folder.
echo It runs on both 32-bit and 64-bit Windows.
echo.
pause

:end
endlocal
