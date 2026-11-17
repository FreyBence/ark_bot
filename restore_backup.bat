@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
if not exist ".venv\Scripts\python.exe" goto missing_setup
".venv\Scripts\python.exe" scripts\restore_backup.py %*
set "ARK_RESTORE_EXIT_CODE=%errorlevel%"
popd
exit /b %ARK_RESTORE_EXIT_CODE%

:missing_setup
echo Run setup.bat first.
popd
exit /b 1
