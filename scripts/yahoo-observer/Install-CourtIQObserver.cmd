@echo off
powershell.exe -NoProfile -File "%~dp0Install-CourtIQObserver.ps1"
if errorlevel 1 pause
