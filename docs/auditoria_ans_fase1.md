# Auditoría ANS/SLA — fase 1

Alcance: inspección estática y pruebas aisladas de referencia. No se modificaron reglas, modelos, configuración, datos ni migraciones. Los hallazgos describen el código disponible, no una verificación del despliegue productivo.

## Fuentes revisadas

- `apps/tickets/models.py`, `sla.py`, `ans_avisos.py`, `views.py`, `views_observador.py`, `views_monitoreo.py`, `views_chat.py`, `decorators.py` y `forms.py`.
- `apps/notificaciones/views.py`, `services.py`, `emails.py`; comando `apps/tickets/management/commands/avisar_ans_por_vencer.py`.
- `templates/tickets/dashboard.html`, `_dashboard_tecnicos_rows.html`, `_ans_time.html`, `detalle.html`, `categorias.html`, `templates/observador/monitoreo.html`, `static/js/dogger.js`; configuración horaria en `config/settings.py`.
- Pruebas existentes `test_ans_en_vivo.py`, `test_ans_observador.py`, `test_dash_pies.py`, `test_observador.py`, `test_tecnico_seguimiento.py`, `apps/notificaciones/tests.py`.

## Reglas y diferencias comprobadas

1. El límite es creación más horas corridas; categoría prevalece si tiene `ans_horas` no nulo/no cero, en otro caso prioridad (urgente 2, alta 8, media 12, baja 48, desconocida 24). `USE_TZ=True`, zona `America/Bogota`. No hay calendario laboral en este cálculo.
2. En activos, `datos_ans` usa vencido en `ahora >= límite` y aviso dos horas antes. Urgente de dos horas está en aviso desde creación. Los temporizadores JS consumen el límite y aviso, pero calculan en el navegador usando su reloj.
3. Finalizados se muestran como `resuelto` sin expresar incumplimiento. `fecha_finalizacion` toma la primera de resolución/cierre disponible. El dashboard usa esa fecha; `_agrupar_vencidos` y parte de las gráficas usan `fecha_cierre`: una resolución a tiempo con cierre tardío puede contabilizarse de modo distinto.
4. Dashboard mezcla activos y finalizados en cumplimiento y excluye finalizados sin fecha terminal. Tabla de técnicos también mezcla activos y finalizados, pero usa la hora actual si falta fecha terminal, por lo que ese último caso no coincide con dashboard. Sus vencidos son solo activos.
5. `_reportes_metricas_kpis` cuenta como cumplidos solamente `info_ans == ok` y como incumplidos `vencido`; excluye `por-vencer` y `resuelto`. Si no hay base devuelve 0 %, no «sin datos». No comparar directamente con el dashboard.
6. Cambiar ANS de categoría cambia plazos calculados retroactivamente; cambiar categoría o prioridad puede cambiar el plazo; reasignar no altera su fórmula. La categoría normalmente eclipsa el cambio de prioridad. No existe una copia histórica del plazo en el ticket identificada en el modelo revisado.
7. Al guardar un ticket abierto/en progreso, `save` limpia `fecha_cierre` y `fecha_resolucion`; no hay en esos campos una primera resolución persistida tras reapertura. Reconstruir historia requiere comprobar otras fuentes y no asumir que son completas.
8. En el límite exacto el estado activo es vencido (`>=`), pero dashboard/tabla consideran `referencia <= límite` como cumplimiento. Esta discrepancia de frontera requiere decisión explícita.
9. La alerta ANS usa marca `ans_alertado_en`, reserva atómica y claves por destinatario/estado; para vencidos existe alerta operativa y el código revisa inactividad/escalamiento según configuración. La campana y el panel de observador pueden disparar revisiones. Existe comando para cron, pero su programación real no se verificó; tampoco se ha demostrado aquí idempotencia bajo concurrencia SQL Server/PostgreSQL ni recuperación completa ante fallos.
10. Los avisos de observadores dependen de elementos seguidos y zonas con `alertas_ans`; el correo de solicitante y técnico se gestiona por los servicios existentes. El alcance y el comportamiento de cambios de responsable tras un aviso requieren pruebas de integración específicas.

## Permisos revisados

- Dashboard, API de sus datos y reportes exigen administrador activo mediante `admin_required`.
- `detalle_ticket` exige staff (administrador/técnico) y su consulta mostrada no se limita al técnico asignado: no afirmar que el detalle general de técnicos esté restringido solo a sus tickets. Los paneles específicos pueden aplicar filtros propios y deben probarse por endpoint.
- `mi_ticket` filtra al punto de venta por correo; el observador usa acceso de lectura asociado a puntos o cuentas de su lista. `_visible_a_observador` devuelve conjunto vacío si no tiene puntos, aunque su docstring dice «vacío = todos»; otras rutas incluyen listas de cuentas, por lo que no debe generalizarse una sola regla para todo observador.
- `tickets_del_observador` limita tickets activos a puntos/correos seguidos, y para alertas a zonas habilitadas. Validaciones de acceso por zona, adjuntos, API, exportaciones, cambios de rol y usuarios inactivos requieren pruebas de integración antes de una garantía integral.

## Pruebas de referencia de esta fase

Archivo `apps/tickets/test_ans_fase1_referencia.py`: pruebas `SimpleTestCase` con objetos en memoria y consultas auxiliares simuladas. Cubren prioridad/categoría, urgente y frontera, cambio de categoría/prioridad/reasignación, reapertura, resolución tardía y diferencia resolución/cierre, discrepancia reportes/dashboard, finalizado sin fecha, decoradores por rol y filtro básico de puntos del observador. Son pruebas de caracterización: algunas fijan comportamientos que deberán cambiar deliberadamente en una fase posterior.

Ejecutar sin crear base ni migrar, en PowerShell:

```powershell
$env:DJANGO_SETTINGS_MODULE='config.settings'
$env:SMOKE_TEST_SQLITE='true'
.\.venv\Scripts\python.exe -c "import django; django.setup(); import unittest; s=unittest.defaultTestLoader.loadTestsFromName('apps.tickets.test_ans_fase1_referencia'); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful())"
```

Las pruebas no sustituyen pruebas de integración, aislamiento multiusuario, navegador, ni pruebas contra SQL Server y PostgreSQL. Estas últimas requieren entornos de prueba aislados y autorización para su preparación/migraciones; no se ejecutaron en esta fase.

## Recomendaciones y decisiones previas a fase 2

1. Definir fuente fiable para plazo histórico y primera resolución, política para registros históricos sin evidencia y etiquetado de datos reconstruidos; no presentar una estimación como dato original.
2. Definir frontera exacta, reaperturas, casos sin fecha, prioridad/categoría y atribución tras reasignación. Mantener 24/7, horas actuales y zona mientras no se autorice otra política.
3. Diseñar migraciones aditivas y respaldo antes de aplicarlas; separar lectura compatible y nuevas métricas de finalizados, sin reemplazar silenciosamente las anteriores.
4. Definir versiones auditadas de configuración, responsables/motivos y alcance de cambios solo a tickets nuevos; toda corrección retroactiva debe ser explícita y auditable.
5. Diseñar pruebas de concurrencia/idempotencia, permisos por endpoint y zona, calendario, notificaciones y diferencias entre motores de base; inspeccionar el programador real antes de prometer avisos autónomos.
6. No activar alertas o escalamiento nuevos hasta aprobación. No se inició fase 2.
