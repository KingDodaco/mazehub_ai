@echo off
setlocal

set "LOG_FILE=%TEMP%\mazehub_launch.log"
> "%LOG_FILE%" echo app=ZBrush

if not defined PIPELINE_DIR set "PIPELINE_DIR=%MAZE_PIPELINE%"

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    echo Launching ZBrush for shot: %MAZE_CONTEXT_NAME%
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    echo Launching ZBrush for asset: %MAZE_CONTEXT_NAME%
) else if "%MAZE_CONTEXT_TYPE%"=="light_rig" (
    echo Launching ZBrush for light rig: %MAZE_CONTEXT_NAME%
)

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"
if not "%MAZE_PROJECT_PIPELINE%"=="" (
    if exist "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat" (
        call "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat"
    ) else if exist "%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio" (
        set "OCIO=%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio"
    )
)

if not defined MAZE_EXE (
    >> "%LOG_FILE%" echo ERROR: MAZE_EXE is not set.
    echo ERROR: MAZE_EXE is not set.
    exit /b 1
)
if not exist "%MAZE_EXE%" (
    >> "%LOG_FILE%" echo ERROR: ZBrush executable not found: "%MAZE_EXE%"
    echo ERROR: ZBrush executable not found: "%MAZE_EXE%"
    exit /b 1
)

>> "%LOG_FILE%" echo MAZE_EXE="%MAZE_EXE%"

if "%~1"=="" (
    start "" "%MAZE_EXE%"
) else (
    start "" "%MAZE_EXE%" "%~1"
)

endlocal
