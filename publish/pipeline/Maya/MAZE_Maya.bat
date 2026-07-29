@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"
set "SCRIPTS_DIR=%PIPELINE_DIR%\Maya\scripts"
set MAYA_SCRIPT_PATH=%SCRIPTS_DIR%

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    set "JOB=%MAZE_CONTEXT_PATH%\maya"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    set "JOB=%MAZE_CONTEXT_PATH%\maya"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
)

set "MAYA_PROJECT=%JOB%"

if defined JOB set "JOB=%JOB:\=/%"

echo Launching Maya for %MAZE_CONTEXT_TYPE%: %MAZE_CONTEXT_NAME%
if defined JOB echo Maya Project=%JOB%
echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE%

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

set "SAFE_SCRIPT_PATH=%SCRIPTS_DIR:\=/%"

set "SET_PROJECT_CMD="
if defined JOB set "SET_PROJECT_CMD=setProject \"%JOB%\"; "

if not "%~1"=="" set "MAZE_OPEN_FILE=%~1"

start "" "C:\Program Files\Autodesk\Maya2025\bin\maya.exe" -command "%SET_PROJECT_CMD%python(\"exec(open('%SAFE_SCRIPT_PATH%/123.py').read())\");"

endlocal