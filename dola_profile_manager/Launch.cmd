@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Run Setup.cmd first.
    pause
    exit /b 1
)
start "Dola Profile Manager" ".venv\Scripts\pythonw.exe" main.py %*
