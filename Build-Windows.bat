@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Installing build dependencies...
python -m pip install -r requirements.txt pyinstaller -q
echo Building Windows application...
python -m PyInstaller --noconfirm --clean --windowed --onefile --name YuqueExporter ^
  --collect-all markdownify --collect-all yaml --collect-all DrissionPage ^
  yuque_export.py
echo.
echo Created: dist\YuqueExporter.exe
pause
