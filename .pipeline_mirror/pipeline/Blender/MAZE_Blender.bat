@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"
set "SCRIPTS_DIR=%PIPELINE_DIR%\Blender\scripts"

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    set "JOB=%MAZE_CONTEXT_PATH%\blender"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    set "JOB=%MAZE_CONTEXT_PATH%\blender"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
)

echo Launching Blender for %MAZE_CONTEXT_TYPE%: %MAZE_CONTEXT_NAME%
echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE%

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

set "SAFE_SCRIPT=%SCRIPTS_DIR:\=/%/startup.py"

start "" "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe" --python "%SAFE_SCRIPT%"

endlocal
