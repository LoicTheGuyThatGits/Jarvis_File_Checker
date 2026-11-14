@echo off
rem Checks that every file Jarvis needs is here and offers to download the missing ones from GitHub.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" filecheck.py --repair %*
) else (
  where py >nul 2>nul && (py -3 filecheck.py --repair %*) || (python filecheck.py --repair %*)
)
echo.
pause
