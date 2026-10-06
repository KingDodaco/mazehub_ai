@echo off
setlocal

set "PIPELINE_DIR=%MAZE_PIPELINE%"

set "HOUDINI_PACKAGE_DIR=%PIPELINE_DIR%\Houdini\Packages"
set "HOUDINI_PATH=%PIPELINE_DIR%\Houdini;&;%HOUDINI_PATH%"
set "HOUDINI_MENU_PATH=%PIPELINE_DIR%\Houdini;&;%HOUDINI_MENU_PATH%"

if not "%MAZE_PROJECT_PIPELINE%"=="" (
    if exist "%MAZE_PROJECT_PIPELINE%\Houdini\Packages" (
        set "HOUDINI_PACKAGE_DIR=%MAZE_PROJECT_PIPELINE%\Houdini\Packages;%HOUDINI_PACKAGE_DIR%"
    )
    if exist "%MAZE_PROJECT_PIPELINE%\Houdini" (
        set "HOUDINI_PATH=%MAZE_PROJECT_PIPELINE%\Houdini;&;%HOUDINI_PATH%"
        set "HOUDINI_MENU_PATH=%MAZE_PROJECT_PIPELINE%\Houdini;&;%HOUDINI_MENU_PATH%"
    )
)

echo Launching USDview...
echo START_FRAME=%START_FRAME%  END_FRAME=%END_FRAME%  FRAME_RATE=%FRAME_RATE%

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"
if not "%MAZE_PROJECT_PIPELINE%"=="" (
    if exist "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat" (
        call "%MAZE_PROJECT_PIPELINE%\OCIO\OCIO_set.bat"
    ) else if exist "%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio" (
        set "OCIO=%MAZE_PROJECT_PIPELINE%\OCIO\BU_nov2024_config.ocio"
    )
)

set "USD_FILE=%MAZE_OPEN_FILE%"

if defined USD_FILE (
    set "USD_FILE_ARG=%USD_FILE:\=/%"
    echo Opening: %USD_FILE%
    start "" "%MAZE_EXE%" "%USD_FILE_ARG%"
) else (
    start "" "%MAZE_EXE%"
)

endlocal
