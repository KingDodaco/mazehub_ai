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
if not "%MAZE_PROJECT_PIPELINE%"=="" (
    if exist "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat" (
        call "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat"
    ) else if exist "%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio" (
        set "OCIO=%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio"
    )
)

if Exist "%MAZE_OPEN_FILE%" (
    set "HOUDINI_FILE_ARG=%MAZE_OPEN_FILE:\=/%"
)

if not "%HOUDINI_FILE_ARG%"=="" (
    start "" "%MAZE_EXE%" "%HOUDINI_FILE_ARG%"
) else (
    start "" "%MAZE_EXE%"
)

endlocal
