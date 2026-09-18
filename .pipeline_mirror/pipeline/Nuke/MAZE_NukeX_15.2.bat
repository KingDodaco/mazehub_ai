@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"
set NUKE_PATH=%PIPELINE_DIR%\Nuke\plugins;%NUKE_PATH%

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    echo Launching NukeX for shot: %MAZE_CONTEXT_NAME%
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    echo Launching NukeX for asset: %MAZE_CONTEXT_NAME%
)

echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE%

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

start "" "C:\Program Files\Nuke15.2v4\Nuke15.2.exe" --nukex "%~1"

endlocal
