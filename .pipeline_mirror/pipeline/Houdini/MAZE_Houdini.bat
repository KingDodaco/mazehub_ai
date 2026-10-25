@echo off
setlocal

set "LOG_FILE=%TEMP%\mazehub_launch.log"

if not defined PIPELINE_DIR set "PIPELINE_DIR=%MAZE_PIPELINE%"

if defined MAZE_CONTEXT_PATH (
    set "JOB=%MAZE_CONTEXT_PATH%\houdini"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
)

if defined JOB if not exist "%JOB%" mkdir "%JOB%"

set "HOUDINI_PACKAGE_DIR=%PIPELINE_DIR%\Houdini\Packages"
set "HOUDINI_PATH=%PIPELINE_DIR%\Houdini;&;%HOUDINI_PATH%"
set "HOUDINI_MENU_PATH=%PIPELINE_DIR%\Houdini;&;%HOUDINI_MENU_PATH%"
set "MPLAY_MENU_PATH=%PIPELINE_DIR%\Houdini;&;%MPLAY_MENU_PATH%"
set "HOUDINI_JOB=%JOB%"
rem Install scripts first so the install 123.py always wins; it runs the project's 123.py itself.
if defined HOUDINI_SCRIPT_PATH (
    set "HOUDINI_SCRIPT_PATH=%PIPELINE_DIR%\Houdini\scripts;%HOUDINI_SCRIPT_PATH%"
) else (
    set "HOUDINI_SCRIPT_PATH=%PIPELINE_DIR%\Houdini\scripts;&"
)

if not "%MAZE_PROJECT_PIPELINE%"=="" (
    if exist "%MAZE_PROJECT_PIPELINE%\Houdini\Packages" (
        set "HOUDINI_PACKAGE_DIR=%MAZE_PROJECT_PIPELINE%\Houdini\Packages;%HOUDINI_PACKAGE_DIR%"
    )
    if exist "%MAZE_PROJECT_PIPELINE%\Houdini" (
        set "HOUDINI_PATH=%MAZE_PROJECT_PIPELINE%\Houdini;&;%HOUDINI_PATH%"
        set "HOUDINI_MENU_PATH=%MAZE_PROJECT_PIPELINE%\Houdini;&;%HOUDINI_MENU_PATH%"
        set "MPLAY_MENU_PATH=%MAZE_PROJECT_PIPELINE%\Houdini;&;%MPLAY_MENU_PATH%"
    )
)

> "%LOG_FILE%" echo app=Houdini
>> "%LOG_FILE%" echo MAZE_CONTEXT_TYPE="%MAZE_CONTEXT_TYPE%"
>> "%LOG_FILE%" echo MAZE_CONTEXT_NAME="%MAZE_CONTEXT_NAME%"
>> "%LOG_FILE%" echo MAZE_CONTEXT_PATH="%MAZE_CONTEXT_PATH%"
>> "%LOG_FILE%" echo JOB="%JOB%"
>> "%LOG_FILE%" echo HOUDINI_JOB="%HOUDINI_JOB%"

echo Launching Houdini for "%MAZE_CONTEXT_TYPE%": "%MAZE_CONTEXT_NAME%"
echo JOB="%JOB%"
echo START_FRAME="%START_FRAME%"  END_FRAME="%END_FRAME%"  FRAME_RATE="%FRAME_RATE%"

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"
if not "%MAZE_PROJECT_PIPELINE%"=="" (
    if exist "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat" (
        call "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat"
    ) else if exist "%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio" (
        set "OCIO=%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio"
    )
)

if not "%~1"=="" set "MAZE_OPEN_FILE=%~1"

if defined MAZE_OPEN_FILE if exist "%MAZE_OPEN_FILE%" (
    set "HOUDINI_FILE_ARG=%MAZE_OPEN_FILE:\=/%"
)

if not defined MAZE_EXE (
    >> "%LOG_FILE%" echo ERROR: MAZE_EXE is not set.
    echo ERROR: MAZE_EXE is not set.
    exit /b 1
)
if not exist "%MAZE_EXE%" (
    >> "%LOG_FILE%" echo ERROR: Houdini executable not found: "%MAZE_EXE%"
    echo ERROR: Houdini executable not found: "%MAZE_EXE%"
    exit /b 1
)

>> "%LOG_FILE%" echo MAZE_EXE="%MAZE_EXE%"

rem Manual mode: start Houdini empty so 123.py runs, switches to Manual and loads the file.
if defined HOUDINI_FILE_ARG if "%MAZE_HOUDINI_MANUAL%"=="1" (
    set "MAZE_HOUDINI_LOAD_FILE=%HOUDINI_FILE_ARG%"
    set "HOUDINI_FILE_ARG="
    >> "%LOG_FILE%" echo MAZE_HOUDINI_MANUAL=1 - loading via 123.py
)

if defined HOUDINI_FILE_ARG (
    start "" "%MAZE_EXE%" "%HOUDINI_FILE_ARG%"
) else (
    start "" "%MAZE_EXE%"
)

endlocal
