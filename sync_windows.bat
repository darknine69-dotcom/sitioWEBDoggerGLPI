@echo off
REM ============================================================
REM  Sincroniza esta carpeta con GitHub (supera el error de
REM  "password_reset_request not found" y trae SMTP + notificaciones
REM  + recuperacion de contrasena por codigo).
REM  Ejecutar con doble clic o desde terminal.
REM  ADVERTENCIA: descarta los cambios locales sin subir.
REM ============================================================
cd /d "%~dp0"

echo [1/4] Descargando los ultimos cambios de GitHub...
git fetch origin
if errorlevel 1 goto :error
git reset --hard origin/master
git clean -fd

echo [2/4] Instalando dependencias...
pip install -r requirements.txt

echo [3/4] Aplicando migraciones (crea tabla de codigos de recuperacion)...
python manage.py migrate
if errorlevel 1 goto :error

echo [4/4] Verificando el proyecto...
python manage.py check
if errorlevel 1 goto :error

echo.
echo ============================================================
echo  LISTO. Proyecto sincronizado con GitHub.
echo  - SMTP      -> configurado en config/settings.py
echo  - Notifs    -> apps/tickets/notifications.py
echo  - Recuperar -> /cuenta/reset/solicitar/
echo    (enlace "Olvidaste tu contrasena?" en el login)
echo ============================================================
pause
exit /b 0

:error
echo.
echo  ERROR: algo fallo. Revisa el mensaje de arriba.
pause
exit /b 1