@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"

if "%MAZE_CONTEXT_TYPE%"=="shot" (
    set "JOB=%MAZE_CONTEXT_PATH%\houdini"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
) else if "%MAZE_CONTEXT_TYPE%"=="asset" (
    set "JOB=%MAZE_CONTEXT_PATH%\houdini"
    set "CONTEXT_NAME=%MAZE_CONTEXT_NAME%"
)

set "HOUDINI_PACKAGE_DIR=%PIPELINE_DIR%\Houdini21.0\Packages"
set "HOUDINI_PATH=%PIPELINE_DIR%\Houdini21.0;&;%HOUDINI_PATH%"
set "HOUDINI_MENU_PATH=%PIPELINE_DIR%\Houdini21.0;&;%HOUDINI_MENU_PATH%"
set "MPLAY_MENU_PATH=%PIPELINE_DIR%\Houdini21.0;&;%MPLAY_MENU_PATH%"
set "HOUDINI_JOB=%JOB%"

echo Launching Houdini for %MAZE_CONTEXT_TYPE%: %MAZE_CONTEXT_NAME%
echo JOB=%JOB%
echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE%

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

if Exist "%MAZE_OPEN_FILE%" (
    set "HOUDINI_FILE_ARG=%MAZE_OPEN_FILE:\=/%"
)

if not "%HOUDINI_FILE_ARG%"=="" (
    start "" "C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\heducation.exe" "%HOUDINI_FILE_ARG%"
) else (
    start "" "C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\heducation.exe"
)

endlocal
