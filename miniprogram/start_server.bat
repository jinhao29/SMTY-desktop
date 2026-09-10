@echo off
REM 启动小程序后端（开发）
cd /d "%~dp0server"
set MP_MODE=shangmen
python main.py
