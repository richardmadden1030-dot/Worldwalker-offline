@echo off
cd /d "%~dp0"
if exist "%~dp0WorldwalkerRPG.exe" (
  start "Worldwalker RPG" "%~dp0WorldwalkerRPG.exe"
  exit /b
)
where py >nul 2>nul
if %errorlevel%==0 (py launcher.py) else (python launcher.py)
pause
