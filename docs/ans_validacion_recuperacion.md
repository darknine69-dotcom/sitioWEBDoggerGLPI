# Validación y recuperación ANS: borrador operativo

No ejecutar sobre producción sin autorización. La familia y versión del motor efectivo deben confirmarse antes de elegir herramientas. El entorno aislado debe usar credenciales y nombres distintos a los reales; nunca proporcionar contraseñas en comandos o registros.

1. Acordar ventana de mantenimiento, responsables, criterios de parada y permisos mínimos. Inventariar base y multimedia sin copiar datos reales sin autorización.
2. Crear respaldo consistente de la base con la herramienta nativa del motor y copia de multimedia en almacenamiento protegido. Registrar fecha, tamaño y huellas criptográficas; comprobar lectura y permisos.
3. Restaurar únicamente una copia autorizada o datos ficticios en una instancia aislada equivalente. Comprobar integridad nativa del motor, recuentos y acceso a archivos restaurados; verificar que no apunte a servicios externos ni produzca notificaciones.
4. En esa instancia, ensayar las migraciones 0047 y 0048 y los escenarios de integridad, concurrencia y rollback. Registrar versiones, resultados y duración. No inferir la validez de SQL Server o PostgreSQL a partir de SQLite.
5. Antes de despliegue real, obtener autorización específica y respaldo verificado. Si falla el ensayo, detener el despliegue. El plan de recuperación debe contemplar restaurar base y multimedia consistentes al mismo punto y documentar la posible pérdida de operaciones posteriores; no deshacer migraciones destructivamente para conservar eventos nuevos.
6. Verificar posteriormente estado de migraciones, muestras autorizadas de tickets e historial, permisos, alertas, GLPI, registros y disponibilidad. Supervisar fallos y tener un responsable para decidir recuperación.

En esta sesión se verificó únicamente un respaldo y restauración de una tabla ficticia entre bases SQLite en memoria (`integrity_check=ok`, un registro restaurado). No es un ensayo del motor de producción, de multimedia, ni una validación de respaldos reales.

Para conocer el motor y migraciones en un entorno con acceso autorizado de solo lectura: `python manage.py estado_bd_ans --entorno produccion`. El argumento es solo una etiqueta declarada, no demuestra por sí mismo que el entorno sea producción. No enviar credenciales ni salida de errores de conexión a terceros.

El comando emite consultas de metadatos, no ejecuta migraciones y rechaza una ruta SQLite inexistente; no otorga ni sustituye permisos de solo lectura del servidor. Debe ejecutarse con una cuenta de consulta autorizada y no se ha validado contra todos los backends. Si el comando aún no está instalado en el despliegue, un administrador puede comunicar exclusivamente motor y versión por un canal seguro sin desplegarlo.

Alternativa cuando Docker no esté disponible: solicitar al administrador una instancia desechable independiente de la misma familia y versión compatible, con usuario limitado a su propia base de pruebas y sin acceso a bases reales. Proporcionar credenciales mediante variables de entorno locales, no por chat ni dentro de documentos; confirmar de forma independiente nombre, servidor y aislamiento antes de ejecutar el test runner. MySQL/MariaDB requiere además ensayar el backend, las migraciones y bloqueos por separado; PostgreSQL y SQL Server no son evidencia de compatibilidad con MySQL. Ninguna de estas instancias se ha proporcionado ni usado en esta sesión.

## Resultado de validación aislada

- Nueva regresión tras corrección de fixtures: 765 pruebas, 14 fallos, 2 errores, 1 omitida en SQLite temporal. La primera ejecución de 762 pruebas quedó truncada y no permite reconstruir una tabla íntegra de sus 48 incidencias. La ejecución focalizada de seguimiento técnico pasó 51 pruebas; dashboard pasó 32; el conjunto encabezados/contadores/técnicos reprodujo 13 fallos en 49 pruebas. No se han resuelto las incidencias restantes ni se debe considerar aprobada la regresión.
- Se confirmó instalado Docker Desktop y contexto `desktop-linux`; el servicio `com.docker.service` figura detenido y el daemon no responde. No se iniciaron servicios ni se cambió la configuración.
- Tres pruebas aisladas del comando de diagnóstico pasaron, incluyendo la que impide crear un archivo SQLite inexistente y la sanitización de errores. Es diagnóstico de lectura a nivel de aplicación, no un mecanismo que conceda permisos de solo lectura en la base.

- Regresión general en SQLite en memoria: 762 pruebas, 28 fallos, 20 errores y una omitida. La ejecución comenzó antes de algunas correcciones de fixtures; no se repitió completa después de ellas. No constituye aprobación de regresión.
- Una ejecución focalizada del dashboard, tras corregir fixtures ANS, terminó con un fallo de interfaz (`chat-scroll`). Dos pruebas de notificaciones que envejecían tickets sin ajustar su instantánea se corrigieron y pasaron al repetirse.
- El comando `estado_bd_ans` tiene dos pruebas aisladas con conexiones simuladas. No se ha probado contra el despliegue real.
- Docker CLI está instalada, pero el daemon no está disponible. Hay controladores PostgreSQL y SQL Server instalados, sin instancias de pruebas aisladas confirmadas. Render declara una base administrada y Compose PostgreSQL 16; cPanel documenta MySQL. Esto no demuestra qué entorno está desplegado.
- `check --deploy` aislado con clave ficticia de prueba suficientemente larga mostró W005 y W021. La política HTTPS de todos los subdominios y la elegibilidad para HSTS preload requieren confirmación del responsable del dominio; no se modificaron esos valores para ocultar advertencias.
