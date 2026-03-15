@echo off
REM ============================================
REM  VisaMintelli AI - One-Time Setup
REM  Run this ONCE on a new machine.
REM  It downloads all dependencies locally.
REM ============================================

echo ==================================================
echo   VisaMintelli AI - Installing Dependencies...
echo ==================================================

REM Install all packages into local 'lib' folder
pip install -r requirements.txt --target lib --upgrade

echo.
echo ==================================================
echo   DONE! Now run launch.bat to start the app.
echo ==================================================
pause
