@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer is required'"
if errorlevel 1 goto :error
py -3 -m venv .venv
if errorlevel 1 goto :error
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo Setup completed. Install Microsoft Edge and/or Google Chrome, then open Launch.cmd.
pause
exit /b 0
:error
echo Setup failed. Install Python 3.11+ from python.org with the Python Launcher enabled.
pause
exit /b 1
