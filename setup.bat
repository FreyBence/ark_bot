@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
if /i "%~1"=="--help" goto help
if not "%~1"=="" if /i not "%~1"=="--install-server" goto usage_error
if not "%~2"=="" goto usage_error

if exist ".venv\Scripts\python.exe" goto dependencies
where py >nul 2>nul
if errorlevel 1 goto python_fallback
py -3 -c "import sys; sys.exit(sys.version_info < (3, 12))"
if errorlevel 1 goto python_fallback
py -3 -m venv .venv
if errorlevel 1 goto failed
goto dependencies

:python_fallback
python -c "import sys; sys.exit(sys.version_info < (3, 12))"
if errorlevel 1 goto missing_python
python -m venv .venv
if errorlevel 1 goto failed

:dependencies
".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info < (3, 12))"
if errorlevel 1 goto missing_python
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\setup_runtime.py %1
if errorlevel 1 goto failed
popd
exit /b 0

:help
echo Usage: setup.bat [--install-server]
echo Installs Python dependencies and SteamCMD; preserves existing .env settings.
echo --install-server also downloads or updates the ARK server. Stop it first.
echo Requires Python 3.12 or newer. Run start_bot.bat after configuring .env.
popd
exit /b 0

:usage_error
echo Unknown argument. Use setup.bat --help.
goto failed

:missing_python
echo Install Python 3.12 or newer from https://www.python.org/downloads/windows/
echo Enable the Python launcher or add Python to PATH, then rerun setup.bat.

:failed
echo Setup failed. Check the error above before retrying.
popd
exit /b 1
