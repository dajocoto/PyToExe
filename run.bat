@echo off
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Checking requirements...
for /F "tokens=* eol=#" %%p in (requirements.txt) do (
    venv\Scripts\pip show %%p >nul 2>&1 || (
        echo   Installing %%p...
        venv\Scripts\pip install %%p --quiet
    )
)

venv\Scripts\python app.py
pause
