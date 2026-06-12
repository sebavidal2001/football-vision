@echo off
REM Analisi Tattica Completa: radar 2D + heatmap + statistiche
cd /d "%~dp0"
python analisi_tattica.py
if errorlevel 1 (
  echo.
  echo Si e' verificato un problema. Assicurati che Python sia installato.
  pause
)
