@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    echo Launching Photoshop for shot: %MAZE_CONTEXT_NAME%
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    echo Launching Photoshop for asset: %MAZE_CONTEXT_NAME%
) else if "%MAZE_CONTEXT_TYPE%"=="light_rig" (
    echo Launching Photoshop for light rig: %MAZE_CONTEXT_NAME%
)

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

start "" "%MAZE_EXE%" "%~1"

endlocal
