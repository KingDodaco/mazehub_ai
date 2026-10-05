@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"

if defined MAZE_CONTEXT_PATH (
    set "JOB=%MAZE_CONTEXT_PATH%\houdini"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
)

set "HOUDINI_PACKAGE_DIR=%PIPELINE_DIR%\Houdini\Packages"
set "HOUDINI_PATH=%PIPELINE_DIR%\Houdini;&;%HOUDINI_PATH%"
set "HOUDINI_MENU_PATH=%PIPELINE_DIR%\Houdini;&;%HOUDINI_MENU_PATH%"
set "MPLAY_MENU_PATH=%PIPELINE_DIR%\Houdini;&;%MPLAY_MENU_PATH%"
set "HOUDINI_JOB=%JOB%"

(
    echo MAZE_CONTEXT_TYPE=%MAZE_CONTEXT_TYPE%
    echo MAZE_CONTEXT_NAME=%MAZE_CONTEXT_NAME%
    echo MAZE_CONTEXT_PATH=%MAZE_CONTEXT_PATH%
    echo JOB=%JOB%
    echo HOUDINI_JOB=%HOUDINI_JOB%
) > "%TEMP%\mazehub_houdini_launch.log"

echo Launching Houdini for %MAZE_CONTEXT_TYPE%: %MAZE_CONTEXT_NAME%
echo JOB=%JOB%
echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE%

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

if Exist "%MAZE_OPEN_FILE%" (
    set "HOUDINI_FILE_ARG=%MAZE_OPEN_FILE:\=/%"
)

if not "%HOUDINI_FILE_ARG%"=="" (
    start "" "%MAZE_EXE%" "%HOUDINI_FILE_ARG%"
) else (
    start "" "%MAZE_EXE%"
)

endlocal
