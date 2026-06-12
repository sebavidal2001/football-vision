@echo off
REM Avvia lo strumento di Calibrazione Campo (Vista Tattica 2D)
cd /d "%~dp0"
python vista_tattica\calibra_campo.py
if errorlevel 1 (
  echo.
  echo Si e' verificato un problema. Assicurati che Python sia installato.
  pause
)
