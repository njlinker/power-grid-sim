@echo off
REM 启动 VeraGrid (原 GridCal) 图形界面
cd /d "%~dp0"
call gridcal-env\Scripts\activate.bat
veragrid
