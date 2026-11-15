@echo off
setlocal
cd /d "%~dp0"
rem  Measures how well your AI model picks Jarvis's tools (Smart commands). Nothing is carried out.
rem  Start Jarvis (or Ollama) first. Add --label to label your own logged messages, --mine to score them too.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py"
"%PY%" tools\router_eval.py %*
echo.
pause
