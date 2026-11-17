@echo off
setlocal
title Build the Jarvis model
cd /d "%~dp0"

rem  Builds the local "jarvis" model in Ollama from model\Modelfile: a base model
rem  (qwen2.5:7b unless you change the FROM line) with Jarvis's settings and manner.
rem  Run it again after changing model\Modelfile. start-jarvis.bat uses "jarvis"
rem  automatically once it exists.

echo ============================================================
echo   Build the Jarvis model
echo ============================================================
echo.

where ollama >nul 2>&1
if errorlevel 1 (
  echo Ollama is not installed. Get it from https://ollama.com/download, then run this again.
  goto end
)

if not exist "model\Modelfile" (
  if not exist "tools\jarvis.Modelfile" (
    echo tools\jarvis.Modelfile is missing. Run repair-jarvis.bat, then try again.
    goto end
  )
  if not exist "model" mkdir "model"
  copy /y "tools\jarvis.Modelfile" "model\Modelfile" >nul
  echo Made model\Modelfile from the template.
)

set "BASE="
for /f "tokens=1,2" %%a in ('findstr /b /i "FROM" "model\Modelfile"') do if not defined BASE set "BASE=%%b"
if not defined BASE (
  echo model\Modelfile has no FROM line, so there is no base model to build on.
  goto end
)
echo Base model: %BASE%
echo If it is not downloaded yet, Ollama fetches it first (qwen2.5:7b is about 4.7 GB).
echo.

rem  Make sure the Ollama server is running.
ollama list >nul 2>&1
if errorlevel 1 (
  start "" /b ollama serve >nul 2>&1
  timeout /t 5 /nobreak >nul
)

echo %BASE% | findstr /r /c:"^\." /c:"\.gguf" >nul
if errorlevel 1 (
  ollama pull %BASE%
  if errorlevel 1 (
    echo Could not download %BASE%. Check the internet connection and try again.
    goto end
  )
)

pushd model
ollama create jarvis -f Modelfile
set "RESULT=%errorlevel%"
popd
if not "%RESULT%"=="0" (
  echo Building the Jarvis model failed. See the message above.
  goto end
)

echo.
echo Quick test:
ollama run jarvis "Introduce yourself in one sentence."
echo.
echo The Jarvis model is ready. Restart Jarvis with start-jarvis-app.bat to use it,
echo or choose "jarvis" in Settings ^> AI model.

:end
echo.
if /i not "%~1"=="--no-pause" pause
