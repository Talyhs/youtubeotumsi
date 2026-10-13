@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo First run run_windows.bat to install dependencies.
  exit /b 1
)
call .venv\Scripts\activate.bat
REM Build the existing video engine as a separate console executable.
python -m PyInstaller --noconfirm --clean --console --name TalyhsEngine ^
  --distpath build_engine\dist --workpath build_engine\work youtube.py
if errorlevel 1 exit /b 1
REM Build the desktop interface as a windowed app.
python -m PyInstaller --noconfirm --clean --windowed --name TalyhsStudio desktop_app.py
if errorlevel 1 exit /b 1
if not exist dist\TalyhsStudio\engine mkdir dist\TalyhsStudio\engine
xcopy /E /I /Y build_engine\dist\TalyhsEngine dist\TalyhsStudio\engine >nul
copy /Y sample_script_10_facts_az.txt dist\TalyhsStudio\sample_script_10_facts_az.txt >nul
echo.
echo Build finished: dist\TalyhsStudio\TalyhsStudio.exe
echo Keep the engine folder beside the app. FFmpeg must be installed and available in PATH.
echo Place your local .env and token.json beside TalyhsStudio.exe. Never upload them to GitHub.
pause
