@echo off
setlocal
title Jarvis
cd /d "%~dp0"

rem ============================================================
rem  Jarvis launcher - double-click this file to start Jarvis.
rem  Keep this window open while you use Jarvis; close it to stop.
rem ============================================================

rem ---- Settings you can change ----------------------------------
rem  USE_LOCAL=1 starts on the Ollama model below, USE_LOCAL=0 on the cloud
rem  (set OPENAI_API_KEY in Windows first). You can switch any time in the
rem  Interface panel > AI model; that choice is remembered in settings.json.
set "USE_LOCAL=1"
rem  "jarvis" is built from model\Modelfile (ollama create jarvis -f model\Modelfile).
rem  If it is not installed, Jarvis starts on FALLBACK_MODEL instead.
set "LOCAL_MODEL=jarvis"
set "FALLBACK_MODEL=llama3.2:3b"
set "JARVIS_ANSWER_STYLE=developed"
rem ---------------------------------------------------------------

rem  Use the private environment made by install-jarvis.bat when it exists.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  where py >nul 2>&1
  if errorlevel 1 (
    echo Python was not found. Run install-jarvis.bat first, or install Python 3.10 or newer from python.org.
    pause
    exit /b 1
  )
  set "PY=py"
  echo Tip: run install-jarvis.bat once to install the packages for computer mode and the system panel.
)

if "%USE_LOCAL%"=="1" (
  set "JARVIS_PROVIDER=local"
  set "JARVIS_LOCAL_MODEL=%LOCAL_MODEL%"
  set "OLLAMA_KEEP_ALIVE=-1"
  tasklist /fi "imagename eq ollama.exe" 2>nul | find /i "ollama.exe" >nul
  if errorlevel 1 (
    echo Starting Ollama...
    start "" /min ollama serve
    timeout /t 4 /nobreak >nul
  )
  ollama show "%LOCAL_MODEL%" >nul 2>&1
  if errorlevel 1 (
    echo The %LOCAL_MODEL% model is not installed; starting on %FALLBACK_MODEL% instead.
    set "JARVIS_LOCAL_MODEL=%FALLBACK_MODEL%"
  )
)

if not "%USE_LOCAL%"=="1" set "JARVIS_PROVIDER=cloud"
rem  App mode (start-jarvis-app.bat): tray icon, own window and hotkey, no console window.
if /i "%~1"=="tray" (
  if not exist "%~dp0data" mkdir "%~dp0data"
  >>"%~dp0data\jarvis-launch.log" echo [%date% %time%] launcher: PY=%PY% arg=%~2
  "%PY%" app\jarvis_tray.py --detach %~2
  exit /b 0
)
echo Starting Jarvis...
"%PY%" app\server.py

echo.
echo Jarvis has stopped.
pause
