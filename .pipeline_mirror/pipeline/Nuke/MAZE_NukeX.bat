@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"
set NUKE_PATH=%PIPELINE_DIR%\Nuke\plugins;%NUKE_PATH%
if not "%MAZE_PROJECT_PIPELINE%"=="" if exist "%MAZE_PROJECT_PIPELINE%\Nuke\plugins" (
    set "NUKE_PATH=%MAZE_PROJECT_PIPELINE%\Nuke\plugins;%NUKE_PATH%"
)

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    echo Launching NukeX for shot: %MAZE_CONTEXT_NAME%
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    echo Launching NukeX for asset: %MAZE_CONTEXT_NAME%
) else if "%MAZE_CONTEXT_TYPE%"=="light_rig" (
    echo Launching NukeX for light rig: %MAZE_CONTEXT_NAME%
)

echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE%

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"
if not "%MAZE_PROJECT_PIPELINE%"=="" (
    if exist "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat" (
        call "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat"
    ) else if exist "%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio" (
        set "OCIO=%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio"
    )
)

start "" "%MAZE_EXE%" --nukex "%~1"

endlocal
