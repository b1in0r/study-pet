@echo off
cd /d "%~dp0"
if exist ".local\hardware-venv\Scripts\python.exe" (
  ".local\hardware-venv\Scripts\python.exe" "tools\open_planner.py"
) else (
  python "tools\open_planner.py"
)
