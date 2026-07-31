@echo off
setlocal

set "PIPELINE_DIR=%PIPELINE_DIR%"

set HOUDINI_PACKAGE_DIR=%PIPELINE_DIR%\Houdini21.0\Packages
set HOUDINI_PATH=^&;%HOUDINI_PATH%

echo Launching usdview...
echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE%

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

set "USD_FILE=%MAZE_OPEN_FILE%"

if defined USD_FILE (
    echo Opening: %USD_FILE%
    start "" "C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\usdview.exe" "%USD_FILE%"
) else (
    start "" "C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\usdview.exe"
)

endlocal
