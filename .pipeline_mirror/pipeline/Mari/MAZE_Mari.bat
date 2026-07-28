@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    echo Launching Mari for shot: %MAZE_CONTEXT_NAME%
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    echo Launching Mari for asset: %MAZE_CONTEXT_NAME%
)

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

start "" "C:\Program Files\Mari\Mari.exe" "%~1"

endlocal
