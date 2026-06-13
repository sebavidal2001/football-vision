@echo off
cd /d "%~dp0"
start "Scout Lab API" powershell -NoExit -Command "cd '%~dp0scout_lab\backend'; python -m pip install -r requirements.txt; python run.py"
start "Scout Lab Frontend" powershell -NoExit -Command "cd '%~dp0scout_lab\frontend'; npm.cmd install; npm.cmd run dev"
start http://127.0.0.1:5173
