@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"
set MAYA_SCRIPT_PATH=%PIPELINE_DIR%\Maya\scripts

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    set "JOB=%MAZE_CONTEXT_PATH%\maya"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    set "JOB=%MAZE_CONTEXT_PATH%\maya"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
)

set "MAYA_PROJECT=%JOB%"

set "JOB=%JOB:\=/%"

echo Launching Maya for %MAZE_CONTEXT_TYPE%: %MAZE_CONTEXT_NAME%
echo Maya Project=%JOB%
echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE%

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

set "SAFE_SCRIPT_PATH=%MAYA_SCRIPT_PATH:\=/%"

start "" "C:\Program Files\Autodesk\Maya2025\bin\maya.exe" -command "setProject \"%JOB%\"; python(\"exec(open('%SAFE_SCRIPT_PATH%/123.py').read())\");"

endlocal