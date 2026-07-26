@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if exist "%PYTHON_EXE%" (
    echo Using project virtual environment...
    "%PYTHON_EXE%" publish_pipeline.py %*
    exit /b %ERRORLEVEL%
)
where py >nul 2>nul
if not errorlevel 1 (
    echo Using py launcher...
    py -3 publish_pipeline.py %*
    exit /b %ERRORLEVEL%
)
where python >nul 2>nul
if not errorlevel 1 (
    echo Using python from PATH...
    python publish_pipeline.py %*
    exit /b %ERRORLEVEL%
)
where python3 >nul 2>nul
if not errorlevel 1 (
    echo Using python3 from PATH...
    python3 publish_pipeline.py %*
    exit /b %ERRORLEVEL%
)
echo No Python interpreter found. Install Python 3.12 or provide a local virtual environment at .venv\Scripts\python.exe.
exit /b 1
