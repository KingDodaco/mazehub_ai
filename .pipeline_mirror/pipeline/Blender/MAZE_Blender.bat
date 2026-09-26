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
) else if "%MAZE_CONTEXT_TYPE%"=="light_rig" (
    set "JOB=%MAZE_CONTEXT_PATH%\blender"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
)

echo Launching Blender for %MAZE_CONTEXT_TYPE%: %MAZE_CONTEXT_NAME%
echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE%

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

set "SAFE_SCRIPT=%SCRIPTS_DIR:\=/%\startup.py"

set "BLEND_FILE=%~1"

if not defined BLEND_FILE if defined MAZE_CONTEXT_PATH (
    set "BLEND_DIR=%MAZE_CONTEXT_PATH%\blender\blend"
    if exist "%BLEND_DIR%\*.blend" (
        for %%f in ("%BLEND_DIR%\*.blend") do set "BLEND_FILE=%%~f"
    )
)

if defined BLEND_FILE (
    echo Opening: %BLEND_FILE%
    start "" "%MAZE_EXE%" "%BLEND_FILE%" --python "%SAFE_SCRIPT%"
) else (
    echo No .blend file specified, starting fresh
    start "" "%MAZE_EXE%" --python "%SAFE_SCRIPT%"
)

endlocal
