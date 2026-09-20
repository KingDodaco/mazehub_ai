@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"

set "HOUDINI_PACKAGE_DIR=%PIPELINE_DIR%\Houdini\Packages"
set "HOUDINI_PATH=%PIPELINE_DIR%\Houdini;&;%HOUDINI_PATH%"
set "HOUDINI_MENU_PATH=%PIPELINE_DIR%\Houdini;&;%HOUDINI_MENU_PATH%"

echo Launching USDview...
echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE%

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

set "USD_FILE=%MAZE_OPEN_FILE%"

if defined USD_FILE (
    set "USD_FILE_ARG=%USD_FILE:\=/%"
    echo Opening: %USD_FILE%
    start "" "%MAZE_EXE%" "%USD_FILE_ARG%"
) else (
    start "" "%MAZE_EXE%"
)

endlocal
