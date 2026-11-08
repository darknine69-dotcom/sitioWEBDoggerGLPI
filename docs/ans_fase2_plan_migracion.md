# ANS fase 2: plan previo de migración y riesgos

Estado: **implementación parcial; no apta para despliegue todavía**. Se generó la migración 0047 y se probó únicamente en SQLite en memoria; no se ha migrado una base existente.

## Implementado y límites actuales

- Continuación: `QuerySet.update`/`bulk_update` rechazan campos históricos y fechas protegidas; la captura inicial usa un método interno. La semilla de desarrollo y fixtures de pruebas usan explícitamente `QuerySet.update` base como excepción controlada; SQL directo o código con acceso interno pueden eludir controles de aplicación. No se ha demostrado protección frente a todos los caminos concurrentes.
- Se agregó formulario y endpoint de ajuste solo para administrador activo, con CSRF, motivo, confirmación, versión y clave. Pruebas ejecutadas en SQLite en memoria: 50 fase 2/ANS en vivo/webhook, 21 fase 2 con CSRF y 35 ANS de observador; aprobadas. No equivale a validación en motores reales ni a regresión integral.
- Docker Compose configura PostgreSQL; Render declara `DATABASE_URL` externa y la alternativa Django es SQL Server si no se configura. Los archivos disponibles no permiten verificar qué motor usa el despliegue real. No se han ejecutado migraciones en bases existentes ni probado respaldos o restauración.

- Se añadió `TicketAjusteANS`, migración 0048 y servicio `ajustar_plazo_ans`: administrador activo, motivo, plazo anterior/nuevo, versión y clave idempotente. La instantánea original no se sobrescribe; la lectura del límite utiliza el ajuste más reciente. El servicio no tiene interfaz ni endpoint asociado. Su control de concurrencia no se ha validado en SQL Server o PostgreSQL y no cubre todas las escrituras del ticket.
- Pruebas ejecutadas: 24 de fase 2 y webhook aprobadas con SQLite 3.50.4 en memoria. `check --deploy` con clave ficticia mostró W005, W009 (clave de prueba) y W021; no acredita la configuración real. No se verificaron respaldo, restauración, secretos ni configuración del despliegue real.

- Protección adicional: `Ticket.save()` compara los campos ANS protegidos con los valores almacenados y rechaza cambios de estado/fechas fuera del servicio, así como cambios de instantánea por `save`. El servicio marca internamente su escritura y retira la marca después. La comparación es a nivel de aplicación y no es un bloqueo de seguridad contra código con acceso interno o SQL directo; además, la comprobación y un `save()` general no constituyen control optimista completo de concurrencia.
- Regresión de esta continuación: 72 pruebas de fase 2, ANS en vivo, contadores, calificación y webhook aprobadas en SQLite temporal. No se ejecutaron pruebas concurrentes en SQL Server/PostgreSQL. `QuerySet.update` todavía permite modificar fechas e instantáneas, y no existe ajuste auditado del plazo; no se debe activar en producción.

- Continuación: el queryset de tickets rechaza cambios directos de `estado` mediante `update` y `bulk_update`; el servicio usa un método interno en la misma transacción que registra el evento. Esto no protege cambios por `save`, otros campos protegidos, el método interno ni SQL directo. Pruebas: 19 de fase 2/webhook y 35 de ANS de observador aprobadas en SQLite en memoria; sin pruebas nuevas de concurrencia real.

- Última continuación: el webhook agrupa su actualización de campos y la transición ANS en una transacción; existe `crear_tickets_ans` como alternativa transaccional al `bulk_create` rechazado. Una prueba fuerza un error al insertar el evento y comprueba el rollback. Se ejecutaron 49 pruebas de fase 2, webhook y ANS del observador en SQLite en memoria; todas pasaron. `makemigrations --check --dry-run` no encontró cambios pendientes.
- La semilla de demostración `seed_prueba` exige `DEBUG` y `--permitir-demo`; ajusta conjuntamente sus fechas ficticias e instantánea ANS en una transacción. Estas fechas no son evidencia de tickets reales. Las modificaciones arbitrarias mediante `QuerySet.update`, `bulk_update`, `save` o SQL directo siguen pudiendo omitir el historial; no se ha comprobado protección completa de las rutas de escritura.
- Se añadió una prueba optativa de dos cierres concurrentes con conexiones independientes, que requiere `DOGGER_ANS_CONCURRENCY_TESTS=1` y una base de pruebas aislada PostgreSQL o SQL Server. Se omitió en SQLite; no constituye validación de esos motores hasta ejecutarse allí. El resto de escenarios concurrentes solicitados sigue pendiente.
- No se dispone de resultados de transacciones concurrentes reales ni pruebas en bases SQL Server o PostgreSQL aisladas. La operación auditada de recálculo continúa pendiente. No se puede afirmar que la fase esté terminada.

- Los tickets creados mediante `Ticket.save()` guardan en una transacción una instantánea verificada de fecha de inicio, límite, horas, prioridad, categoría y fuente. Los tickets históricos quedan como `desconocido` y conservan el cálculo dinámico provisional.
- Se agregó `TicketTransicionANS` y un servicio transaccional que serializa con `select_for_update`, comprueba el estado esperado y registra transiciones/ciclos. Lo usan la acción individual del panel, cierre del solicitante y cierre masivo.
- El webhook GLPI ahora usa el servicio de transición. La creación masiva por el queryset de tickets se rechaza porque omitiría `save`. **Pendiente crítico:** `QuerySet.update`, SQL directo y cualquier otra ruta que no use el servicio pueden omitir el historial; no hay garantía integral ni operación auditada de recálculo.
- El servicio añade una actualización condicional del estado para detectar conflictos. No se verificó concurrencia real ni bloqueo en SQL Server o PostgreSQL; no se debe asumir que `select_for_update` proporcione en SQL Server las mismas garantías que en PostgreSQL.
- La instantánea de creación modifica deliberadamente el comportamiento de los fixtures que cambian `fecha_creacion` directamente: deben ajustar también la instantánea si quieren simular una creación histórica.
- En la continuación se ejecutaron 45 pruebas de fase 2, webhook y ANS de observador, y después 12 de fase 2 y webhook con los últimos cambios, en SQLite efímero. No acreditan concurrencia ni compatibilidad completa con todos los módulos.

## Antecedentes y restricciones

El plazo actual se calcula dinámicamente en `Ticket.fecha_limite_ans`; la resolución y el cierre se limpian al reabrir en `Ticket.save`. Congelar un plazo calculado con la configuración actual de una categoría no demuestra que esa fuera la configuración al crear un ticket antiguo. Los registros antiguos sin evidencia deben conservar procedencia desconocida y no deben marcarse como plazo original confirmado.

El campo `fecha_creacion` usa `auto_now_add`. El diseño de captura inicial debe usar exactamente el instante persistido, sin provocar una segunda escritura parcial que pueda quedar desincronizada por error o concurrencia. El historial de transición y la actualización del ticket deben confirmarse atómicamente y preservar comportamiento de `update_fields`. Hay que tratar guardados concurrentes, ediciones sin cambio de estado, cierres directos y reaperturas repetidas.

## Propuesta a validar

1. Migración solo de esquema, aditiva: campos anulables para límite, horas, prioridad y categoría aplicada (incluyendo texto o identificador estable si la categoría se elimina), procedencia y momento de captura; tabla de eventos con ticket, tipo, fecha, procedencia e identificador de deduplicación. Sin `RunPython` que invente plazos históricos.
2. Nuevos tickets: capturar un único plazo y sus datos de entrada de forma transaccional al crearse; luego la propiedad existente debe leer la instantánea. Para registros antiguos sin evidencia, mantener explícitamente la lectura compatible actual y señalar que no es un plazo histórico verificado.
3. Guardar eventos de resolución, cierre y reapertura sin borrar historia; conservar las columnas existentes y su semántica de ciclo para no cambiar silenciosamente reportes, notificaciones ni GLPI. Comprobar transiciones con bloqueo apropiado y una marca de resolución inicial independiente del ciclo vigente.
4. Inspeccionar eventos existentes como fuente histórica y distinguir fechas verificables de ausentes. Cualquier importación histórica o ajuste explícito requiere una operación separada, idempotente, auditable y aprobación previa.
5. Auditar llamadas a `update`, operaciones masivas, importaciones, trabajos GLPI y scripts administrativos: Django no invoca `save` en `QuerySet.update`. La búsqueda inicial detectó `seed_prueba.py` para fechas y la marca de aviso en `ans_avisos.py`; no es una demostración exhaustiva de todos los caminos de escritura.
6. Probar en bases temporales aisladas SQL Server y PostgreSQL, con respaldo y restauración de prueba, verificar cambios de esquema, concurrencia, reversibilidad operativa, y compatibilidad con paneles, reportes y avisos. No se han realizado estas pruebas.

## Activación propuesta

Revisar diff y migración generada; verificar respaldo y restauración; ensayar en una copia aislada con ambas bases; comparar indicadores anteriores y posteriores, con especial atención a los no verificables; aprobar por separado la migración del entorno real y despliegue. Conservar plan de reversión que no elimine el historial generado. No activar indicadores nuevos, reglas de notificación ni escalamientos durante esta fase.
