@echo off

setlocal

set NUKE_PATH=%PIPELINE_DIR%\Nuke\plugins

call "%PIPELINE_DIR%\OCIO\OCIO_set.bat"

"C:\Program Files\Nuke15.2v4\Nuke15.2.exe" --nukex REM --x --execute "nuke.root"

endlocal