@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"
set "SCRIPTS_DIR=%PIPELINE_DIR%\Maya\scripts"
set MAYA_SCRIPT_PATH=%SCRIPTS_DIR%
set "MAZE_123=%SCRIPTS_DIR%\123.py"

if not "%MAZE_PROJECT_PIPELINE%"=="" (
    if exist "%MAZE_PROJECT_PIPELINE%\Maya\scripts" (
        set "MAYA_SCRIPT_PATH=%MAZE_PROJECT_PIPELINE%\Maya\scripts;%SCRIPTS_DIR%"
    )
    if exist "%MAZE_PROJECT_PIPELINE%\Maya\scripts\123.py" (
        set "MAZE_123=%MAZE_PROJECT_PIPELINE%\Maya\scripts\123.py"
    )
)

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    set "JOB=%MAZE_CONTEXT_PATH%\maya"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    set "JOB=%MAZE_CONTEXT_PATH%\maya"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
) else if "%MAZE_CONTEXT_TYPE%"=="light_rig" (
    set "JOB=%MAZE_CONTEXT_PATH%\maya"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
)

if defined JOB if not exist "%JOB%" mkdir "%JOB%"

set "MAYA_PROJECT=%JOB%"

if defined JOB set "JOB=%JOB:\=/%"

echo Launching Maya for %MAZE_CONTEXT_TYPE%: %MAZE_CONTEXT_NAME%
if defined JOB echo Maya Project=%JOB%
echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE%

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"
if not "%MAZE_PROJECT_PIPELINE%"=="" (
    if exist "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat" (
        call "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat"
    ) else if exist "%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio" (
        set "OCIO=%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio"
    )
)

set "SAFE_SCRIPT_PATH=%MAZE_123:\=/%"

set "SET_PROJECT_CMD="
if defined JOB set "SET_PROJECT_CMD=setProject \"%JOB%\"; "

if not "%~1"=="" set "MAZE_OPEN_FILE=%~1"

start "" "%MAZE_EXE%" -command "%SET_PROJECT_CMD%python(\"exec(open('%SAFE_SCRIPT_PATH%').read())\");"

endlocal
