@echo off
cd /d "%~dp0"
start "VeraGridServer" cmd /k "chcp 65001 >nul && set PYTHONUTF8=1&& set PYTHONIOENCODING=utf-8&& gridcal-env\Scripts\python.exe -m VeraGridServer.run --host 127.0.0.1 --port 8000 --secure False"
