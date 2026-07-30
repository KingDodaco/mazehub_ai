@echo off

set "PIPELINE_DIR=%MAZE_PIPELINE%"
set "SUBSTANCE_PLUGINS=%PIPELINE_DIR%\Substance\plugins"

if defined SUBSTANCE_PAINTER_PLUGIN_PATH (
    set "SUBSTANCE_PAINTER_PLUGIN_PATH=%SUBSTANCE_PLUGINS%;%SUBSTANCE_PAINTER_PLUGIN_PATH%"
) else (
    set "SUBSTANCE_PAINTER_PLUGIN_PATH=%SUBSTANCE_PLUGINS%"
)

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    echo Launching Substance Painter for shot: %MAZE_CONTEXT_NAME%
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    echo Launching Substance Painter for asset: %MAZE_CONTEXT_NAME%
)

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

start "" "C:\Program Files\Adobe\Adobe Substance 3D Painter\Adobe Substance 3D Painter.exe" "%~1"
