@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
call gridcal-env\Scripts\activate.bat
python -m VeraGridServer.run --host 127.0.0.1 --port 8000 --secure False
