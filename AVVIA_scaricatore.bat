@echo off
REM Avvia lo Scaricatore Clip con doppio click
cd /d "%~dp0"
python scaricatore_clip.py
if errorlevel 1 (
  echo.
  echo Si e' verificato un problema. Assicurati che Python sia installato.
  pause
)
