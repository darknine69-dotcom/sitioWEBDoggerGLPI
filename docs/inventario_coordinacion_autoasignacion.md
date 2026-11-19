# Inventario de coordinación de carga y elegibilidad

El orden previsto es configuración global, después ticket, dentro de la misma transacción. Esta tabla documenta el estado de la revisión; no sustituye una prueba concurrente en SQL Server.

| Escritura | Estado de coordinación |
| --- | --- |
| Selección automática, rotación y auditoría | Bloqueo global y ticket en `services/autoasignacion_transaccional.py`. |
| Asignación manual en bandeja, detalle, panel y lote | Usa `asignar_manual`; vuelve a leer el ticket bajo bloqueo. |
| Edición del solicitante (prioridad, categoría y punto) | Toma el bloqueo global antes del ticket en `views.py`. |
| Transiciones ANS y webhook GLPI de estado | Ahora toman el bloqueo global antes de escribir el ticket; el webhook toma el bloqueo antes de su propia actualización. |
| Comando `eliminar_demo` | Desasignación manual coordinada y eliminación bajo el bloqueo global. La auditoría protegida puede impedir eliminar un técnico con decisiones históricas. |
| Ajustes de reglas y perfiles en pantalla Dogger | Toman el bloqueo global para las escrituras y relaciones. |
| Administrador Django: reglas, perfiles y categorías | Las solicitudes POST de cambio y listado editable toman el bloqueo global, incluso durante guardado M2M. |
| Categorías desde vistas Dogger: actualización, activación y eliminación | Ahora toman el bloqueo global. |
| Alta mediante `crear_tickets_ans` | Ahora toma el bloqueo global antes de guardar tickets preasignados. |
| Otras altas con técnico preasignado, comandos de carga o semillas | **Pendiente de coordinación integral**; pueden agregar carga sin pasar por la selección automática. |
| Alta, edición, activación y eliminación de cuentas desde el panel Dogger | Ahora toman el bloqueo global antes de modificar el usuario. |
| Cambio de rol voluntario en ajustes | La escritura del rol toma el bloqueo global. |
| Otros cambios de rol, activo e is_active, sincronización GLPI y comandos de cuentas | **Pendiente**: afectan elegibilidad y no todas las rutas toman el bloqueo global. |
| Cambios de puntos activos, ajustes por procesos externos, SQL directo y escrituras ORM de terceros | **Pendiente de auditoría y coordinación**. |
| Borrado lógico, restauración o eliminación de tickets y señales asociadas | **Pendiente de validación** frente a los managers y filtros que usa el cálculo de carga. |
| Cambios de preferencias, adjuntos y comentarios | No alteran por sí mismos la carga ponderada o elegibilidad. |

El bloqueo solo es eficaz cuando todas las escrituras relevantes cooperan. Las tareas de GLPI y notificaciones deben quedar fuera de la transacción que protege la decisión; su entrega e idempotencia requieren pruebas adicionales. Los tests SQLite no demuestran serialización.
