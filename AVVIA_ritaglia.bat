@echo off
REM Avvia il Ritaglia Clip in Locale con doppio click
cd /d "%~dp0"
python ritaglia_locale.py
if errorlevel 1 (
  echo.
  echo Si e' verificato un problema. Assicurati che Python sia installato.
  pause
)
