@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"
set "MAZE_BAT_LOG=%TEMP%\mazehub_houdini_launch.log"
echo [%date% %time%] MAZE_Houdini_21.0.bat > "%MAZE_BAT_LOG%"
echo PIPELINE_DIR=%PIPELINE_DIR% >> "%MAZE_BAT_LOG%"
echo MAZE_PIPELINE=%MAZE_PIPELINE% >> "%MAZE_BAT_LOG%"
echo MAZE_CONTEXT_TYPE=%MAZE_CONTEXT_TYPE% >> "%MAZE_BAT_LOG%"
echo MAZE_CONTEXT_NAME=%MAZE_CONTEXT_NAME% >> "%MAZE_BAT_LOG%"
echo MAZE_CONTEXT_PATH=%MAZE_CONTEXT_PATH% >> "%MAZE_BAT_LOG%"

set "JOB=%MAZE_CONTEXT_PATH%\houdini"
set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"

set HOUDINI_PACKAGE_DIR=%PIPELINE_DIR%\Houdini21.0\Packages
set HOUDINI_PATH=%PIPELINE_DIR%\Houdini21.0;^&;%HOUDINI_PATH%
set HOUDINI_JOB=%JOB%

echo HOUDINI_PATH=%HOUDINI_PATH% >> "%MAZE_BAT_LOG%"
echo HOUDINI_PACKAGE_DIR=%HOUDINI_PACKAGE_DIR% >> "%MAZE_BAT_LOG%"
echo HOUDINI_JOB=%HOUDINI_JOB% >> "%MAZE_BAT_LOG%"
echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE% >> "%MAZE_BAT_LOG%"
echo MAZE_OPEN_FILE=%MAZE_OPEN_FILE% >> "%MAZE_BAT_LOG%"

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"
echo OCIO=%OCIO% >> "%MAZE_BAT_LOG%"

set "HOUDINI_FILE_ARG=%MAZE_OPEN_FILE:\=/%"

if defined HOUDINI_FILE_ARG (
    start "" "C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\heducation.exe" "%HOUDINI_FILE_ARG%"
) else (
    start "" "C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\heducation.exe"
)

echo [done] >> "%MAZE_BAT_LOG%"
endlocal
