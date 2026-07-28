@echo off
setlocal

set "ROOT=%~dp0"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
set "DIST=%ROOT%dist"
set "BUILD=%ROOT%build"
set "APP_NAME=MazeHub"

echo ========================================
echo  MazeHub Build Script
echo ========================================

rem Use project venv if available
set "PY_EXE=python"
if exist "%VENV_PY%" (
    set "PY_EXE=%VENV_PY%"
    echo Using project venv: %VENV_PY%
) else (
    echo Using system Python...
)

rem Clean previous builds
echo Cleaning previous builds...
taskkill /f /im MazeHub.exe >nul 2>nul
timeout /t 2 /nobreak >nul
if exist "%BUILD%" rmdir /s /q "%BUILD%"
if exist "%DIST%" rmdir /s /q "%DIST%"

rem Build with --console so errors are visible; change to --windowed for release
set "WINDOW_FLAG=--console"

echo Building %APP_NAME% (console mode for debugging)...
"%PY_EXE%" -m PyInstaller ^
    --onefile ^
    %WINDOW_FLAG% ^
    --name "%APP_NAME%" ^
    --add-data ".pipeline_mirror\pipeline;pipeline" ^
    --add-data "make_folders.py;." ^
    --collect-all PySide6 ^
    --hidden-import pipeline_gui ^
    --hidden-import pipeline_app ^
    --hidden-import recent_files ^
    "%ROOT%main.py"

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    exit /b 1
)

echo.
echo ========================================
echo  Build complete: %DIST%\%APP_NAME%.exe
echo ========================================
echo.
echo Debug log will be at: %%TEMP%%\mazehub_debug.log
echo.
pause
