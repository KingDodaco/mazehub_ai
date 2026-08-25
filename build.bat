@echo off
setlocal

set "ROOT=%~dp0"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
set "DIST=%ROOT%dist"
set "BUILD=%ROOT%build"
set "APP_NAME=MazeHub"
set "ICON_PNG=%ROOT%MazeHub_Logo.png"
set "ICON_ICO=%ROOT%MazeHub_Logo.ico"

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

rem Convert PNG to ICO if needed
if exist "%ICON_PNG%" (
    echo Converting logo to ICO format...
    "%PY_EXE%" -c "from PIL import Image; img = Image.open(r'%ICON_PNG%'); img.save(r'%ICON_ICO%', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
    if errorlevel 1 (
        echo Warning: ICO conversion failed, building without icon
        set "ICON_FLAG="
    ) else (
        set "ICON_FLAG=--icon=%ICON_ICO%"
    )
) else (
    echo No logo found at %ICON_PNG%, building without icon
    set "ICON_FLAG="
)

rem Clean previous builds
echo Cleaning previous builds...
taskkill /f /im MazeHub.exe >nul 2>nul
timeout /t 2 /nobreak >nul
if exist "%BUILD%" rmdir /s /q "%BUILD%"
if exist "%DIST%" rmdir /s /q "%DIST%"

rem Build with --windowed so no console window appears
set "WINDOW_FLAG=--windowed"

echo Building %APP_NAME% (console mode for debugging)...
"%PY_EXE%" -m PyInstaller ^
    --onefile ^
    %WINDOW_FLAG% ^
    %ICON_FLAG% ^
    --name "%APP_NAME%" ^
    --add-data ".pipeline_mirror\pipeline;pipeline" ^
    --add-data "make_folders.py;." ^
    --add-data ".venv\Lib\site-packages\Imath.py;." ^
    --add-binary ".venv\Lib\site-packages\OpenEXR.cp312-win_amd64.pyd;." ^
    --collect-all PySide6 ^
    --collect-all numpy ^
    --collect-all PIL ^
    --hidden-import pipeline_gui ^
    --hidden-import pipeline_app ^
    --hidden-import recent_files ^
    --hidden-import OpenEXR ^
    --hidden-import Imath ^
    --hidden-import numpy ^
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
