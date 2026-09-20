@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
) else if "%MAZE_CONTEXT_TYPE%"=="light_rig" (
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
)

set "HOUDINI_PACKAGE_DIR=%PIPELINE_DIR%\Houdini\Packages"
set "HOUDINI_PATH=%PIPELINE_DIR%\Houdini;&;%HOUDINI_PATH%"
set "HOUDINI_MENU_PATH=%PIPELINE_DIR%\Houdini;&;%HOUDINI_MENU_PATH%"

echo Launching usdview (Houdini 21.0)...
echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE%

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

set "USD_FILE=%MAZE_OPEN_FILE%"

if defined USD_FILE (
    set "USD_FILE_ARG=%USD_FILE:\=/%"
    echo Opening: %USD_FILE%
    start "" "C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\usdview.cmd" "%USD_FILE_ARG%"
) else (
    start "" "C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\usdview.cmd"
)

endlocal
