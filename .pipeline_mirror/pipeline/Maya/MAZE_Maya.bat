@echo off

setlocal

set MAYA_SCRIPT_PATH=%PIPELINE_DIR%\Maya\scripts

if "%1"=="-clean" (
    echo running with clean environment variables
) else (
    if not "%ASSET%"=="" (
        if not "%SHOT%"=="" (
            echo ERROR: SHOT and ASSET are both set!
            exit /b 1
        ) else (
            set "JOB=%ASSET%\maya"
        )
    ) else (
        if not "%SHOT%"=="" (
            set "JOB=%SHOT%\maya"
        ) else (
            echo ERROR: SHOT or ASSET are not set!
            exit /b 1
        )
))

set "JOB=%JOB:\=/%"
echo "%JOB%"

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

set "SAFE_SCRIPT_PATH=%MAYA_SCRIPT_PATH:\=/%"

start "" "C:\Program Files\Autodesk\Maya2025\bin\maya.exe" -command "setProject \"%JOB%\"; python(\"exec(open('%SAFE_SCRIPT_PATH%/123.py').read())\");"

endlocal