@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"
set "SUBSTANCE_PLUGINS=%PIPELINE_DIR%\Substance"

if defined SUBSTANCE_PAINTER_PLUGINS_PATH (
    set "SUBSTANCE_PAINTER_PLUGINS_PATH=%SUBSTANCE_PLUGINS%;%SUBSTANCE_PAINTER_PLUGINS_PATH%"
) else (
    set "SUBSTANCE_PAINTER_PLUGINS_PATH=%SUBSTANCE_PLUGINS%"
)

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    echo Launching Substance Painter for shot: %MAZE_CONTEXT_NAME%
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    echo Launching Substance Painter for asset: %MAZE_CONTEXT_NAME%
)

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

start "" "%MAZE_EXE%" "%~1"

endlocal
