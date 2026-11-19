# Resumen semanal de tickets

La suscripción es individual y está desactivada por defecto. El resumen cuenta los tickets solicitados por el usuario y los creados en la semana anterior que actualmente tiene asignados; no incluye tickets generales por rol o zona. La semana se interpreta de lunes a lunes en America/Bogota.

Primero configure y pruebe SMTP. `python manage.py enviar_resumen_semanal` solo muestra cuántas cuentas están suscritas y no envía mensajes. El comando `python manage.py enviar_resumen_semanal --enviar` envía correos reales a las cuentas suscritas; debe programarlo un responsable autorizado los lunes a las 08:00 hora de Bogotá. Si el servidor usa UTC, corresponde a las 13:00 UTC. Configure la tarea en el programador del servidor o Cron Jobs de cPanel con el entorno virtual, el directorio y las variables de entorno de la aplicación. El comando valida que sea lunes después de las 08:00 de Bogotá; no instala ni activa una tarea automáticamente.

Se registra una reserva por cuenta y semana antes de enviar. Una interrupción o un error de SMTP deja el estado reservado o en revisión, sin reintento automático, porque el servidor podría haber aceptado el mensaje. Revise el resultado antes de intervenir. SMTP no permite garantizar entrega exactamente una vez. El resumen no modifica tickets ni necesita migraciones nuevas.

## Programación en cPanel

El archivo `scripts/resumen_semanal_cpanel.sh` prepara la ejecución desde el directorio del proyecto y exige indicar `DOGGER_PYTHON` con la ruta absoluta del intérprete del entorno virtual. En Cron Jobs, configure el horario de los lunes a las 08:00 de Bogotá, teniendo en cuenta la zona horaria efectiva del servidor. Por ejemplo, si el servidor usa UTC, la expresión es `0 13 * * 1`. Configure las variables de Django mediante el mecanismo seguro del hosting; no escriba contraseñas en la línea del cron. La instalación de este archivo no crea ni habilita una tarea programada.
