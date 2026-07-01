@echo off
REM Builds PyToExe itself into a standalone Windows executable.
setlocal
cd /d "%~dp0"
pip install -r requirements.txt
python -m PyInstaller app.py --name PyToExe --onefile --windowed --clean --noconfirm
echo Done. See dist\PyToExe.exe
endlocal
