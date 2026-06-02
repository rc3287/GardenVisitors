@echo off
setlocal enabledelayedexpansion
title GardenVisitors — Build

echo ============================================
echo  GardenVisitors — Build executable
echo ============================================
echo.

:: Find Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH.
    echo         Install Python from https://python.org and try again.
    pause & exit /b 1
)

:: Use a separate Windows venv to avoid WSL artefacts
set VENV=venv-win
if not exist %VENV%\Scripts\python.exe (
    echo [1/4] Creating Windows virtual environment...
    python -m venv %VENV%
    if %errorlevel% neq 0 ( echo [ERROR] venv creation failed. & pause & exit /b 1 )
) else (
    echo [1/4] Windows venv already exists, reusing.
)

echo [2/4] Installing dependencies...
%VENV%\Scripts\pip install -q --upgrade pip
%VENV%\Scripts\pip install -q -r requirements.txt pyinstaller
if %errorlevel% neq 0 ( echo [ERROR] pip install failed. & pause & exit /b 1 )

echo [3/4] Building executable...
%VENV%\Scripts\pyinstaller ^
    --name GardenVisitors ^
    --onedir ^
    --windowed ^
    --collect-all PyQt6 ^
    --hidden-import cv2 ^
    --hidden-import PIL ^
    --hidden-import PIL.Image ^
    --clean ^
    main.py

if %errorlevel% neq 0 ( echo [ERROR] PyInstaller failed. & pause & exit /b 1 )

echo [4/4] Done.
echo.
if exist dist\GardenVisitors\GardenVisitors.exe (
    echo  Executable : dist\GardenVisitors\GardenVisitors.exe
    echo  To distribute: copy the entire dist\GardenVisitors\ folder.
) else (
    echo [WARNING] Expected exe not found — check output above.
)
echo.
pause
