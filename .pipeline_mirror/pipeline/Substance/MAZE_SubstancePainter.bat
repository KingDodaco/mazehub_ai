@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    echo Launching Substance Painter for shot: %MAZE_CONTEXT_NAME%
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    echo Launching Substance Painter for asset: %MAZE_CONTEXT_NAME%
)

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

start "" "C:\Program Files\Adobe\Adobe Substance 3D Painter\Adobe Substance 3D Painter.exe" "%~1"

endlocal
