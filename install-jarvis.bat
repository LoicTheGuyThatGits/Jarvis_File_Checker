@echo off
setlocal
title Jarvis setup
cd /d "%~dp0"

echo ============================================================
echo   Jarvis setup - installs what Jarvis needs into this folder
echo ============================================================
echo.

rem ---- 1. Python 3.10 or newer ----
where py >nul 2>&1
if errorlevel 1 goto nopython
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto nopython
goto havepython

:nopython
echo Python 3.10 or newer was not found on this PC.
where winget >nul 2>&1
if errorlevel 1 (
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  echo Then run this file again.
  pause
  exit /b 1
)
choice /c YN /n /m "Install Python 3.12 now with winget? [Y/N] "
if errorlevel 2 (
  echo Cancelled.
  pause
  exit /b 1
)
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
echo.
echo Python is installed. Close this window and run install-jarvis.bat again.
pause
exit /b 0

:havepython
rem Prefer Python 3.12 or 3.13: the newest Python often has no ready-made packages yet (voice notes need them).
set "PYSEL=-3"
py -3.12 -c "pass" >nul 2>&1
if not errorlevel 1 set "PYSEL=-3.12"
if "%PYSEL%"=="-3" (
  py -3.13 -c "pass" >nul 2>&1
  if not errorlevel 1 set "PYSEL=-3.13"
)
for /f "delims=" %%v in ('py %PYSEL% --version') do echo Found %%v

rem ---- 2. A private environment inside this folder ----
if not exist ".venv\Scripts\python.exe" goto makeenv
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info < (3, 14) else 1)" >nul 2>&1
if not errorlevel 1 goto haveenv
if "%PYSEL%"=="-3" goto haveenv
echo The private environment uses a very new Python that some packages do not support yet.
echo Rebuilding it with the Python found above...
rmdir /s /q ".venv"
:makeenv
echo.
echo Creating a private Python environment in the .venv folder...
py %PYSEL% -m venv .venv
if errorlevel 1 (
  echo Could not create the environment.
  pause
  exit /b 1
)
:haveenv

rem ---- 3. Packages (PyAutoGUI, Pillow, psutil, pystray, pypdf) ----
echo.
echo Installing packages. This needs internet and takes a minute or two...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 echo Could not update pip, continuing anyway.
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pipfail
".venv\Scripts\python.exe" -c "import pyautogui, PIL, psutil, pystray, pypdf; print('All packages are working.')"
if errorlevel 1 goto pipfail
echo Adding voice-note support (local speech recognition, optional)...
".venv\Scripts\python.exe" -m pip install --upgrade faster-whisper av
if errorlevel 1 echo Could not add voice-note support. Jarvis works fine without it. If your Python is 3.14 or newer, install Python 3.12 with: winget install -e --id Python.Python.3.12 and run install-jarvis.bat again.

rem ---- 4. What should Jarvis call you? ----
echo.
if not exist "data" mkdir "data"
if exist "address.txt" if not exist "data\address.txt" move /y "address.txt" "data\address.txt" >nul
set "CURRENT="
if exist "data\address.txt" set /p CURRENT=<"data\address.txt"
if not defined CURRENT goto askaddress
echo Jarvis currently calls you: %CURRENT%
choice /c YN /n /m "Keep that? [Y/N] "
if not errorlevel 2 goto addressdone
:askaddress
echo What should Jarvis call you?
echo   1 = sir
echo   2 = ma'am
echo   3 = something else (you type it)
choice /c 123 /n /m "Choose 1, 2 or 3: "
if errorlevel 3 goto addresscustom
if errorlevel 2 goto addressmadam
>"data\address.txt" echo sir
goto addressdone
:addressmadam
>"data\address.txt" echo ma'am
goto addressdone
:addresscustom
".venv\Scripts\python.exe" app\set-address.py
:addressdone

rem ---- 5. Start with Windows? ----
echo.
echo Jarvis can run as an app: a tray icon, its own window, and the hotkey Ctrl+Alt+J.
choice /c YN /n /m "Start Jarvis in the tray when Windows starts? [Y/N] "
if errorlevel 2 (
  ".venv\Scripts\python.exe" app\jarvis_tray.py --autostart off >nul
) else (
  ".venv\Scripts\python.exe" app\jarvis_tray.py --autostart on
)

rem ---- 5b. Desktop shortcut with the Jarvis icon ----
echo.
choice /c YN /n /m "Put a Jarvis shortcut with its icon on the desktop? [Y/N] "
if not errorlevel 2 ".venv\Scripts\python.exe" app\jarvis_tray.py --shortcut

rem ---- 6. Optional: the local AI model ----
echo.
where ollama >nul 2>&1
if errorlevel 1 (
  echo Ollama is not installed. It is only needed for the local AI model.
  echo Get it from https://ollama.com/download when you have a fast connection,
  echo or use the cloud: open start-jarvis.bat and set USE_LOCAL=0.
  goto finished
)
echo Ollama was found.
ollama show jarvis >nul 2>&1
if not errorlevel 1 (
  echo The Jarvis model is already built.
  goto askvision
)
echo The Jarvis model is a local model with Jarvis's manner built in, on qwen2.5:7b.
echo It needs about 4.7 GB and works best with a graphics card of 6 GB or more.
choice /c YN /n /m "Build the Jarvis model now? [Y/N] "
if errorlevel 2 goto asksmall
call build-jarvis-model.bat --no-pause
goto askvision

:asksmall
choice /c YN /n /m "Download the smaller llama3.2:3b model instead? It is about 2 GB. [Y/N] "
if errorlevel 2 goto askvision
ollama pull llama3.2:3b

:askvision
echo.
ollama list 2>nul | findstr /i "gemma3 llava vision minicpm-v moondream qwen2.5vl" >nul 2>&1
if not errorlevel 1 (
  echo A vision model is already installed, so Jarvis can read photos.
  goto finished
)
echo A vision model lets Jarvis read the photos you send it on Telegram.
choice /c YN /n /m "Download the small vision model moondream now? It is about 1.7 GB. [Y/N] "
if errorlevel 2 goto finished
ollama pull moondream
if errorlevel 1 echo Could not download the vision model. Run: ollama pull moondream later to retry.

:finished
echo.
echo ============================================================
echo   Setup finished. Start Jarvis with start-jarvis-app.bat
echo ============================================================
choice /c YN /n /m "Start Jarvis now? [Y/N] "
if errorlevel 2 exit /b 0
call "%~dp0start-jarvis-app.bat"
exit /b 0

:pipfail
echo.
echo The packages did not install. Check your internet connection and run this file again.
echo Jarvis still works without them, but computer mode and the system panel will be limited.
pause
exit /b 1
