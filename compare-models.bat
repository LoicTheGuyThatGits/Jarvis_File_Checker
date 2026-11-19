@echo off
setlocal
cd /d "%~dp0"
rem  Compares local AI models on the same questions: speed, automatic checks, and the answers side by side.
rem  Examples:  compare-models.bat --models jarvis,llama3.2:3b      compare-models.bat --mine --smart
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py"
"%PY%" tools\model_bench.py %*
echo.
pause
