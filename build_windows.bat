@echo off
REM Heins True Diyae Pro 2.0 - Windows build (run from this folder, in cmd or by double-click)
REM Result: dist\HeinsTrueDiyaePro\HeinsTrueDiyaePro.exe  (ship the whole HeinsTrueDiyaePro folder)
setlocal
cd /d "%~dp0"
if not exist .venv (
    py -3.12 -m venv .venv || python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip || goto :error
pip install -r requirements.txt pyinstaller || goto :error
pyinstaller HeinsTrueDiyaePro.spec --noconfirm --clean || goto :error
echo.
echo Build OK: dist\HeinsTrueDiyaePro\HeinsTrueDiyaePro.exe
goto :eof
:error
echo.
echo Build failed - see the messages above.
exit /b 1
