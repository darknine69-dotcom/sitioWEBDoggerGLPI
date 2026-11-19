# Validación previa al despliegue de autoasignación

Estado: **pendiente; no activar en producción**. Esta lista no autoriza despliegue ni migraciones.

## Entorno aislado

- Preparar un servidor SQL Server y una base de pruebas exclusivos, con credenciales sin acceso a producción. Confirmar que Django creará y eliminará únicamente la base de pruebas: el corredor crea la base antes de ejecutar las comprobaciones de las clases de test.
- Configurar el nombre explícito de la base de test con prefijo `test_` o sufijo `_test`; comprobar el servidor, nombre y permisos antes de ejecutar nada.
- Ejecutar las pruebas de `apps.tickets.test_concurrencia_sqlserver` con `RUN_SQLSERVER_CONCURRENCY_TESTS=1`. Verificar que no se omiten y registrar versión del servidor, backend, aislamiento y resultados. SQLite no valida estos bloqueos.
- Probar creación simultánea desde varios puntos, saturación, asignación y desasignación manual concurrentes, rotación y cambios de estado o prioridad durante la selección.

## Integridad de rutas y datos

- Auditar las escrituras que cambian asignación, estado, prioridad, capacidad, elegibilidad o cobertura para que sigan el mismo orden de bloqueo; revisar especialmente comandos administrativos y sincronización GLPI.
- Investigar el comando `eliminar_demo`: desasigna por actualización masiva y no usa el bloqueo global. No ejecutarlo durante la validación del motor.
- Verificar la conservación de asignaciones manuales, incluidas desasignaciones, y revisar qué hacer con registros históricos que no permiten identificar una desasignación manual anterior a la nueva marca.
- Ensayar migraciones 0049–0053 en una copia anónima y recuperable, revisar dependencias e índices y probar reversión. No ejecutarlas en la base real durante la validación.

## Integración y operación

- Comprobar que el panel muestre perfiles y ocupación, y que solo las cuentas autorizadas modifiquen reglas o el estado del motor.
- Comprobar alertas por ausencia de candidatos y saturación, deduplicación y reintento; verificar recepción efectiva por administradores habilitados.
- Usar un GLPI de pruebas: verificar identificador del técnico, fallos remotos, reintentos y ausencia de notificaciones duplicadas. Revisar los técnicos sin ID GLPI.
- Verificar copia de seguridad, restauración y monitoreo de errores; preparar un responsable y un procedimiento para desactivar el motor y gestionar manualmente tickets pendientes.
- Solo tras aprobación y pruebas exitosas, planificar la aplicación de migraciones, perfiles y activación con una ventana controlada. Este documento no constituye una instrucción para ejecutarlas.
