@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo First run run_windows.bat to install dependencies.
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m PyInstaller --noconfirm --clean --windowed --name TalyhsStudio desktop_app.py
echo.
echo Build finished. Check dist\TalyhsStudio\TalyhsStudio.exe
echo FFmpeg must be installed separately and available in PATH.
pause
