@echo off
setlocal
cd /d "%~dp0"
if exist "MazeHub.exe" (
    start "" "MazeHub.exe"
    exit /b 0
)
echo MazeHub.exe not found in %~dp0
exit /b 1
