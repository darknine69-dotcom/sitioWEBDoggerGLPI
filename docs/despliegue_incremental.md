# Paquetes incrementales: uso experimental

Esta herramienta no despliega automáticamente ni ejecuta migraciones. Es una preparación local; no se ha validado en cPanel, Python 3.12, MySQL ni con múltiples instaladores simultáneos. **No autoriza ni certifica producción.** El ZIP no está firmado: recíbalo solo de una fuente confiable y verifique su procedencia fuera de la herramienta. El filtro de secretos es una ayuda, no garantiza detectar todos los secretos. Revise los archivos antes de incluirlos.

## Preparar en Windows

Desde la raíz del proyecto, seleccione explícitamente cada archivo revisado. Ejemplo de un paquete que contiene el código de los avisos:

```powershell
.\tools\deploy\generar.ps1 -Salida "$env:TEMP\dogger_update.zip" -Archivos @('apps/notificaciones/emails.py','apps/tickets/notifications.py')
.\.venv\Scripts\python.exe tools/deploy/paquete.py --validar "$env:TEMP\dogger_update.zip"
```

La salida no debe existir previamente. La herramienta incluye el contenido actual del archivo, que puede no estar confirmado en Git; usa `HEAD` para calcular la versión base esperada. Inspeccione `git diff` y archivos nuevos. No admite borrados ni migraciones; estas requieren un procedimiento separado. Excluye `.env`, `media`, cachés, entornos virtuales y archivos fuera de su lista de extensiones y carpetas.

Si Git no está instalado o no hay un `HEAD` accesible, se pueden seleccionar archivos explícitamente, pero no se puede acreditar su versión base: el instalador solo permitirá añadirlos cuando no existan ya en el destino. No debe sortearse esta protección.

## Ensayo aislado antes de cPanel

El instalador compara el hash del archivo destino con el de la versión base del repositorio local. Si no coinciden, detiene la operación; no sobreescriba archivos distintos a ciegas. Use primero una copia aislada con datos sintéticos y compruebe aplicación y restauración. Un directorio de bloqueo evita dos ejecuciones simultáneas de esta herramienta; no protege frente a cambios de otros programas. Si un proceso termina abruptamente, el bloqueo puede quedar y requiere revisión manual antes de retirarlo.

```powershell
.\.venv\Scripts\python.exe tools/deploy/paquete.py --instalar "$env:TEMP\dogger_update.zip" --raiz "C:\ruta\copia-aislada" --dry-run
```

## Ejecución posterior en cPanel, solo con autorización

1. Asegure un respaldo independiente y probado de base de datos, configuración y archivos multimedia. Compruebe la raíz real y que sea `/home/halimenh2/Dogger`; no use el instalador si no puede recuperarse ante un corte.
2. En una ubicación privada bajo `tools/deploy/`, coloque los scripts de esta carpeta y el ZIP con nombre `dogger_update.zip`. La carga inicial de estos scripts debe revisarse de forma independiente: no permita que un ZIP suministre el código que lo valida.
3. Configure `DOGGER_DEPLOY_ROOT` con la raíz verificada, mediante las variables seguras de Setup Python App. Ejecute `tools/deploy/paquete.py` sin argumentos: solo simula. Revise el resultado y resuelva cualquier conflicto manualmente, sin sobrescribir `.env` ni `media`.
4. Solo si se autoriza el cambio, ejecute `tools/deploy/aplicar_cpanel.py`. Registre el ID de respaldo impreso. La herramienta no reinicia Passenger, no instala dependencias, no ejecuta `collectstatic` ni migra datos.
5. Si procede una restauración, pare los procesos de actualización, configure `DOGGER_DEPLOY_BACKUP_ID` con el ID obtenido y ejecute `tools/deploy/restaurar_cpanel.py`. La restauración se detiene si un archivo aplicado cambió después; puede eliminar únicamente archivos creados por ese paquete cuyo hash siga coincidiendo. La recuperación completa de la aplicación puede requerir restaurar el respaldo independiente.
6. Para Python, reinicie la aplicación únicamente cuando esté autorizado mediante la opción de reinicio de Setup Python App. Para CSS/JS, confirme cómo sirve estáticos el hosting: si utiliza `STATIC_ROOT`, coordine `collectstatic` y compruebe el recurso servido; no borre archivos estáticos a ciegas.
7. `tools/deploy/comprobar_cpanel.py` comprueba configuraciones sin mostrar secretos, cuenta las tareas y consulta migraciones sin aplicarlas. Solo ejecutarlo en el entorno autorizado. No envía correo ni modifica tickets; no prueba entrega, restauración ni concurrencia.

El comando `procesar_tareas` sin `--loop` procesa una tarea por ejecución. No active Cron automáticamente ni reintente una tarea de entrega incierta sin verificar primero con el destinatario. La ruta de Python virtual de cPanel y la disponibilidad de Cron deben confirmarse con el proveedor.

## Riesgos conocidos

El backend Graph se obtuvo del archivo aportado localmente, no de una comparación verificada con cPanel. Deben confirmarse versión, dependencias `msal`, variables y remitente. Los errores HTTP 429/503 no interpretan `Retry-After`: quedan para revisión, sin reintento automático. Las excepciones de terceros podrían contener información sensible en trazas; revise la política de logs antes de producción. La entrega del backend y la cola deben ensayarse en un entorno aislado equivalente a MySQL. No se ha verificado el funcionamiento de Setup Python App ni la integridad de respaldos reales. Los permisos, la semántica de `os.replace` y la recuperación después de una interrupción deben validarse en el hosting.
