@echo off
cd /d "%~dp0"
call gridcal-env\Scripts\activate.bat
jupyter lab --notebook-dir="%~dp0" --ip=127.0.0.1 --port=8888
