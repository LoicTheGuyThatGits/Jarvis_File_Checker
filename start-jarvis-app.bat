@echo off
rem  Starts Jarvis as an app: tray icon, its own window and the Ctrl+Alt+J hotkey.
rem  Double-click this instead of start-jarvis.bat. Add the word "hidden" to start in the tray only.
call "%~dp0start-jarvis.bat" tray %*
