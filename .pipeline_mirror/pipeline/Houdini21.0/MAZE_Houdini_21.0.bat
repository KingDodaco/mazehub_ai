@echo off

setlocal

set HOUDINI_PACKAGE_DIR=%PIPELINE_DIR%\Houdini21.0\Packages
set HOUDINI_PATH=%PIPELINE_DIR%\Houdini21.0

if "%1"=="-clean" (
    echo running with clean environment variables
) else (
    if not "%ASSET%"=="" (
        if not "%SHOT%"=="" (
            echo ERROR: SHOT and ASSET are both set!
            exit /b 1
        ) else (
            set "JOB=%ASSET%\houdini"
        )
    ) else (
        if not "%SHOT%"=="" (
            set "JOB=%SHOT%\houdini"
        ) else (
            echo ERROR: SHOT or ASSET are not set!
            exit /b 1
        )
))

echo "%JOB%"

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

start "" "C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\heducation.exe"

endlocal