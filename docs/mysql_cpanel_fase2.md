# Preparación MySQL y cPanel: Fase 2 ANS

Estado: pendiente de validación en MySQL aislado y no autorizado para despliegue.
El proveedor debe confirmar que ofrece MySQL (no asumir que MariaDB es igual),
su versión, Python compatible con las dependencias, Passenger o Setup Python App,
un mecanismo seguro de variables de entorno y capacidad de ejecutar comandos.

## Configuración

Crear una aplicación aislada y proporcionar `DOGGER_DB_ENGINE=mysql`,
`DATABASE_URL=mysql://USUARIO:CLAVE@SERVIDOR:PUERTO/BASE` mediante el gestor
de secretos del hosting; codificar los caracteres especiales de la URL. No guardar
valores reales en archivos versionados. Configurar `DJANGO_DEBUG=False`, una
`DJANGO_SECRET_KEY` aleatoria, hosts y orígenes CSRF explícitos, HTTPS y cookies
seguras. Confirmar requisitos de correo, cifrado y cola durable del proyecto.
`utf8mb4` se fija en la conexión; crear la base con ese conjunto de caracteres y
verificar su cotejamiento, modo estricto y zona horaria. La hora ANS sigue siendo
continua 24/7 y la zona de aplicación America/Bogota.

El proyecto utiliza PyMySQL como adaptador; Django recomienda mysqlclient. La
compatibilidad real entre versiones de Django, Python, controlador y MySQL debe
ensayarse en el hosting antes de utilizarla. SQL Server local se mantiene con
`DOGGER_DB_ENGINE=mssql` y sus variables actuales. Sin `DATABASE_URL` y con
DEBUG desactivado, la selección de SQL Server debe ser explícita.

## Aplicación y archivos

Configurar Passenger para cargar `passenger_wsgi.py` desde la raíz del proyecto,
si el proveedor soporta esa modalidad. Si utiliza otra interfaz, confirmar el
punto de entrada con el proveedor. Publicar archivos estáticos mediante
`collectstatic` en una ubicación independiente y configurar su servicio en el
servidor. Mantener adjuntos privados fuera del directorio público y conservar el
control de acceso de Django; no exponer todo MEDIA_ROOT como archivos públicos.
No asumir disponibilidad de SSH: confirmar si la interfaz permite instalar
dependencias, ejecutar tareas y reiniciar la aplicación; de lo contrario pedir
al proveedor un mecanismo autorizado.

## Ensayo aislado obligatorio

Usar una instancia y credenciales exclusivas de prueba, sin datos reales. Django
puede crear y destruir bases al ejecutar `manage.py test`: verificar previamente
que la configuración y los permisos apunten exclusivamente a ese entorno. Verificar
versión y `SELECT @@default_storage_engine`, y revisar en information_schema que
las tablas pertinentes usan InnoDB. Ensayar la cadena completa de migraciones,
incluidas 0047 y 0048, con datos sintéticos anteriores a ellas. Comparar registros,
plazos desconocidos, índices, claves foráneas y restricciones antes y después.
MySQL puede realizar DDL con confirmaciones implícitas: no asumir rollback de
migraciones; practicar recuperación mediante restauración de respaldo.

Con `DOGGER_ANS_CONCURRENCY_TESTS=1`, ejecutar el módulo de concurrencia en la
base aislada. Actualmente cubre únicamente dos cierres simultáneos; resolución,
reapertura, ajustes, GLPI y conflictos aún necesitan pruebas independientes.
Ejecutar después la batería completa contra MySQL aislado. Registrar versión,
resultados y omisiones; SQLite no sustituye estos ensayos.

## Respaldo y recuperación

En pruebas, crear datos sintéticos y archivos multimedia de muestra. Exportar SQL
desde la herramienta MySQL de cPanel disponible, con estructura y datos; verificar
que incluya claves e índices. Respaldar por separado los archivos multimedia.
Restaurar únicamente en otra base y directorio aislados, comparar recuentos,
claves foráneas y archivos mediante hashes, y ejecutar comprobaciones funcionales.
Documentar versión, duración, responsable y resultados. Para producción, acordar
ventana de mantenimiento, respaldo verificable, restauración y autorización antes
de cualquier migración; ante fallo detener la aplicación y recuperar la copia
ensayada sin borrar información generada después sin una decisión explícita.
