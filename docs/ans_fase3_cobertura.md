# Cobertura ANS: integración en curso

No constituye certificación de producción. Los números de línea pueden cambiar;
la clasificación se refiere a las funciones indicadas.

| Archivo / función | Consumidor y situación | Pruebas relevantes |
| --- | --- | --- |
| `tickets/models.py`, `datos_ans` | Adaptador compatible de estados activos al motor; cerrado conserva presentación heredada. | `test_ans_en_vivo`, `test_motor_ans` |
| `tickets/services/motor_ans.py`, `calcular_ans`, `historial_ans`, `evaluar_lote` | Motor, historial y evaluación por lote; las categorías sin instantánea son compatibilidad provisional. | `test_motor_ans`, `test_motor_ans_historial` |
| `tickets/ans_avisos.py`, `por_vencer`, `_enviar_aviso_reclamado` | Selección y duración de avisos con motor; selección por bloques. | `test_ans_observador`, `notificaciones/tests.py` |
| `notificaciones/services.py`, recordatorios de prioritarios | Estado vencido del motor por lote. | `notificaciones/tests.py` |
| `tickets/views.py`, `_dashboard_metricas`, `_dashboard_sparks` | Métricas y series de cumplimiento mediante motor. | `test_ans_consistencia_motor`, `test_dash_pies` |
| `tickets/views.py`, `_build_chart_context`, `_build_tecnico_dashboard` | Estados para gráficas, pivotes y comparativos proceden de `evaluar_lote`; la duración histórica usa el estado terminal del motor. | `test_dash_pies`, `test_dashboard_rol_tecnico`, `test_motor_ans_historial` |
| `tickets/views.py`, `_zona_dashboard`, `_mi_zona_supervisor` | Conteos de vencidos y vigentes mediante `evaluar_lote`; horas de resolución siguen siendo duración operativa. | `test_mi_zona`, `test_monitoreo_zonas` |
| `tickets/views.py`, `_dashboard_atencion`, `tec_tickets_api` | Prioridad de atención y presentación del ANS mediante el resultado del lote. | `test_dashboard_rol_tecnico` |
| `tickets/views.py`, `_agrupar_vencidos`, `_brecha_cerrada`, carga por técnico | Clasificación histórica de incumplimiento mediante motor; desconocidos excluidos. | `test_ans_fase1_referencia`, `test_dashboard_rol_tecnico` |
| `tickets/views.py`, filtro de exportación | Vencidos usa motor; selección de fechas de vencimiento es un filtro de calendario. | Regresión integral pendiente de esta versión |
| `tickets/views.py`, bandeja y filtros `vencidas` / `vencen-hoy` | `evaluar_lote` aporta límite y estado; fechas locales delimitan el día. | `test_ans_en_vivo`, `test_predeploy_ans` |
| `tickets/views.py`, orden y filtro de vencimiento de la cola técnica | `evaluar_lote`, con selección por fecha local y estado. | `test_dashboard_rol_tecnico`, `test_ans_en_vivo` |
| `tickets/views_observador.py`, `_estado_de`, `_contar_por_estado`, `_resumen_por_punto`, `panel_observador`, indicadores activos | Estado mediante motor por lote; fechas por día son agrupación de calendario. | `test_observador`, `test_monitoreo_zonas`, `test_motor_ans_historial` |
| `tickets/views_monitoreo.py`, `views_chat.py` | Consumen `datos_ans` / `info_ans` y por tanto el adaptador; algunas fechas se muestran u ordenan. | `test_ans_observador`, `test_chat_widget` |
| `tickets/views.py`, `_reportes_metricas_kpis` | KPI ANS con `evaluar_lote`; los históricos insuficientes se excluyen del cumplimiento definitivo. | `test_ans_consistencia_motor`, `test_motor_ans_historial`, `test_exportes` |
| `tickets/views.py`, `_eventos_panel_punto` | Vencimiento de actividad del solicitante con `evaluar_lote`, preservando el filtro de su correo. | `test_actividad_punto`, `test_ans_consistencia_motor` |
| `tickets/views.py`, `_punto_venta_panel_datos` | Estados y serie ANS calculados por lote; el plazo terminal corresponde al evento histórico. | `test_actividad_punto`, `test_ans_consistencia_motor` |
| `tickets/views.py`, agrupaciones restantes del observador y reportes | Integración parcial: algunas lecturas de límite sirven para presentación o agrupación, pero faltan pruebas comparativas y mediciones N+1 por ruta y rol. | Pendiente de cobertura completa |
| `tickets/services/transiciones_ans.py`, instantáneas y ajuste | Escrituras de Fase 2, no cálculo de clasificación para paneles; no se modificaron. | `test_ans_fase2` |
| `tickets/management/commands/seed_prueba.py` | Excepción de desarrollo con fechas artificiales, no clasificación productiva. | `test_predeploy_ans` |

La prueba de lotes mide una y nueve instancias con ajustes y dos consultas con
historial; otro caso verifica la carga por lote de categorías de históricos
provisionales. Además, un caso mide 1, 10, 50 y 200 tickets en el lote y en los
KPI de reportes, con dos y una consulta respectivamente. Se evalúa de nuevo desde base en cada llamada, sin guardar el
resultado en una caché persistente. El límite práctico de parámetros SQL y el
rendimiento en MySQL siguen pendientes de medición; la ruta de avisos usa bloques
de 200. No se ha demostrado eliminación de N+1 en todos los consumidores.

Los KPI del dashboard se probaron con 1, 10, 50 y 200 tickets activos: cinco
consultas totales para métricas y dos para series, incluyendo consultas que no
son ANS. Los ajustes y transiciones se consultan en bloques de hasta 500 ids.
La incertidumbre de secuencias contradictorias se propaga al resultado terminal
del motor y a las métricas del dashboard y reportes (`test_ans_consistencia_motor`).

`_build_tecnico_dashboard` y `_contar_por_estado` se probaron con uno y diez
tickets ajustados: las consultas a ajustes/transiciones no aumentaron con el
tamaño en ese intervalo. La segunda función realizó una consulta ANS en ambos
casos. Aún no se han medido todas las rutas HTTP de los distintos roles ni los
tamaños 50 y 200 para esas dos funciones.

Pendientes: revisar y sustituir los cálculos restantes, evaluar ciclos incompletos
y contradicciones, probar consistencia por todos los roles y evaluar migraciones,
concurrencia y recuperación en una instancia MySQL aislada y autorizada.
