@echo off
setlocal
cd /d "%~dp0"
rem  Writes data\training\jarvis-finetune.jsonl from the answers you marked with a thumbs-up.
rem  Add --include-unrated to also keep answers you never rated.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py"
"%PY%" app\export_training.py %*
echo.
pause
