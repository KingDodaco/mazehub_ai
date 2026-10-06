@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"
set "SUBSTANCE_PLUGINS=%PIPELINE_DIR%\Substance"
if not "%MAZE_PROJECT_PIPELINE%"=="" if exist "%MAZE_PROJECT_PIPELINE%\Substance" (
    set "SUBSTANCE_PLUGINS=%MAZE_PROJECT_PIPELINE%\Substance;%SUBSTANCE_PLUGINS%"
)

if defined SUBSTANCE_PAINTER_PLUGINS_PATH (
    set "SUBSTANCE_PAINTER_PLUGINS_PATH=%SUBSTANCE_PLUGINS%;%SUBSTANCE_PAINTER_PLUGINS_PATH%"
) else (
    set "SUBSTANCE_PAINTER_PLUGINS_PATH=%SUBSTANCE_PLUGINS%"
)

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    echo Launching Substance Painter for shot: %MAZE_CONTEXT_NAME%
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    echo Launching Substance Painter for asset: %MAZE_CONTEXT_NAME%
) else if "%MAZE_CONTEXT_TYPE%"=="light_rig" (
    echo Launching Substance Painter for light rig: %MAZE_CONTEXT_NAME%
)

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"
if not "%MAZE_PROJECT_PIPELINE%"=="" (
    if exist "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat" (
        call "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat"
    ) else if exist "%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio" (
        set "OCIO=%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio"
    )
)

start "" "%MAZE_EXE%" "%~1"

endlocal
