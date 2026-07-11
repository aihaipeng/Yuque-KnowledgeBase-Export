@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Checking dependencies...
python -m pip install -r requirements.txt -q
start "" pythonw.exe yuque_export.py
