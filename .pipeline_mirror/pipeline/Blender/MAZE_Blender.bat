@echo off
setlocal

set "LOG_FILE=%TEMP%\mazehub_launch.log"
> "%LOG_FILE%" echo app=Blender

if not defined PIPELINE_DIR set "PIPELINE_DIR=%MAZE_PIPELINE%"
set "SCRIPTS_DIR=%PIPELINE_DIR%\Blender\scripts"
rem The install startup.py always runs; it runs the project's startup.py (if any) itself.
set "MAZE_STARTUP=%SCRIPTS_DIR%\startup.py"

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
if not "%MAZE_PROJECT_PIPELINE%"=="" (
    if exist "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat" (
        call "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat"
    ) else if exist "%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio" (
        set "OCIO=%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio"
    )
)

set "SAFE_SCRIPT=%MAZE_STARTUP:\=/%"

set "BLEND_FILE=%~1"

set "BLEND_DIR="
if defined MAZE_CONTEXT_PATH set "BLEND_DIR=%MAZE_CONTEXT_PATH%\blender\blend"

if not defined BLEND_FILE if defined BLEND_DIR if exist "%BLEND_DIR%\*.blend" (
    for %%f in ("%BLEND_DIR%\*.blend") do set "BLEND_FILE=%%~f"
)

if not defined MAZE_EXE (
    >> "%LOG_FILE%" echo ERROR: MAZE_EXE is not set.
    echo ERROR: MAZE_EXE is not set.
    exit /b 1
)
if not exist "%MAZE_EXE%" (
    >> "%LOG_FILE%" echo ERROR: Blender executable not found: "%MAZE_EXE%"
    echo ERROR: Blender executable not found: "%MAZE_EXE%"
    exit /b 1
)

>> "%LOG_FILE%" echo MAZE_EXE="%MAZE_EXE%"

if defined BLEND_FILE (
    echo Opening: %BLEND_FILE%
    start "" "%MAZE_EXE%" "%BLEND_FILE%" --python "%SAFE_SCRIPT%"
) else (
    echo No .blend file specified, starting fresh
    start "" "%MAZE_EXE%" --python "%SAFE_SCRIPT%"
)

endlocal
