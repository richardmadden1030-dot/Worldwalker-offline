@echo off
if exist "%~dp0WorldwalkerRPG.exe" (
  start "Worldwalker Phone Host" "%~dp0WorldwalkerRPG.exe" --lan
) else (
  start "Worldwalker Phone Host" python "%~dp0launcher.py" --lan
)
