@echo off
REM Build ED-MQTT-Telemetry.exe on Windows.
REM Run this from a Windows machine with Python 3.10+ installed.

setlocal
cd /d "%~dp0"

echo Creating virtual environment...
python -m venv build_venv
call build_venv\Scripts\activate.bat

echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

echo Building executable with PyInstaller...
pyinstaller --noconfirm --onefile --windowed ^
    --name "ED-MQTT-Telemetry" ^
    --icon assets\icon.ico ^
    --paths src ^
    src\main.py

echo.
echo Done. Find your executable at dist\ED-MQTT-Telemetry.exe
endlocal
pause
