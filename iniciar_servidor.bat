@echo off
REM ---------------------------------------------------------------------------
REM  Dogger - Mesa de Ayuda TI
REM  Levanta el servidor local y abre el navegador cuando ya este listo.
REM  Para detenerlo: cerrar esta ventana o pulsar Ctrl+C.
REM ---------------------------------------------------------------------------
cd /d "%~dp0"
title Dogger - Mesa de Ayuda TI (127.0.0.1:8000)

echo.
echo   Iniciando Dogger en http://127.0.0.1:8000/
echo   Deja esta ventana abierta mientras trabajes.
echo.
start "" cmd /c "timeout /t 7 /nobreak >nul && start "" http://127.0.0.1:8000/"

.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000

echo.
echo   El servidor se detuvo.
pause
