# Checklist Pre-Despliegue

**Worker Docker — avance:** `docker-compose.yml` incluye el servicio `worker` bajo el perfil `durable`; comprueba las migraciones antes de consumir trabajos y se reinicia si aún no están listas. La configuración de Compose se validó con una contraseña temporal, sin construir ni arrancar contenedores. Para activarlo, configurar una `DOGGER_FERNET_KEY` estable y `DOGGER_FONDO_DURABLE=True` en `.env`, y arrancar con `docker compose --profile durable up -d --build`. Web y worker deben compartir la misma clave y base de datos. La activación requiere previamente respaldo y pruebas de migraciones, caídas y entrega en el entorno de despliegue; el hallazgo sigue parcial hasta validar el servicio real y su supervisión.

**Actualización adicional de validación:** Compose valida su configuración con una contraseña temporal y rechaza ejecutarse sin contraseña de PostgreSQL. Se reforzó la validación de imágenes contra bombas de descompresión y se verificó que una imagen falsificada no modifica el ticket. Pasaron 30 pruebas de ANS del observador, 28 de seguridad/configuración/permisos y 17 de filtros de resolución. La suite completa con `--failfast` llegó a 266 pruebas y detectó una expectativa antigua por el renderizado simultáneo de tabla y tarjetas; al revisarla se corrigió además el distintivo indebido de «Resuelto» en cierres directos. Se lanzó una nueva suite completa, todavía sin resultado al redactar esta actualización. Los estados y bloqueantes de la tabla siguen vigentes; faltan validar la suite completa y la infraestructura real.

**SQL Server local:** el entorno tiene `mssql-django` 1.8.0, `pyodbc` 5.3.0 y ODBC Driver 18 instalados. Se verificó únicamente la presencia de los componentes, no la conexión, compatibilidad de esquema, migraciones ni transacciones contra un servidor SQL Server. Los cambios de Django y Compose deben validarse en un entorno de pruebas equivalente al de despliegue.

**Última ejecución completa disponible:** con `--failfast` avanzó hasta 298 pruebas y se detuvo en una prueba que seleccionaba el primer «Ranking de zonas» de la página después de agregar un segundo ranking. Se corrigió el alcance de esa prueba y pasó individualmente. Las 15 pruebas de papelera también pasaron tras distinguir los tickets activos de los eventos de actividad y respetar la regla actual de resolución. Es necesaria otra ejecución completa antes de declarar la suite aprobada.

**Pruebas adicionales:** `git diff --check` terminó sin errores de espacios (solo advertencias de finales de línea). El módulo de permisos/seguridad y las comprobaciones focalizadas ejecutaron 28 pruebas exitosas; el módulo ANS del observador ejecutó 30 y la clase de filtros de resolución ejecutó 17. Se ha vuelto a iniciar la suite completa con `--failfast`, sin resultado final todavía.

**Regla de visibilidad confirmada y corregida:** un punto asignado a una carpeta puede ver datos generales de los puntos de la lista del supervisor; sin asignación no ve esos agregados. Se limitó el pivote a datos agregados y se excluyeron los detalles de tickets. Pasaron 38 pruebas de Mi zona, alcance, actividad y contadores, incluidos casos sin carpeta, sin supervisor, con otro supervisor y con un nombre de punto coincidente.

**Resultado más reciente de suite completa:** 300 pruebas ejecutadas con `--failfast`; una falló en la regla de visibilidad descrita arriba, que después se corrigió y validó mediante pruebas enfocadas. No se ejecutaron las pruebas posteriores y la suite completa todavía no está aprobada. Las validaciones son con SQLite aislada, no con SQL Server ni servicios reales.

**Validación posterior de Monitoreo:** una ejecución aislada de `apps.tickets.test_monitoreo_zonas` se detuvo en `test_miembro_muestra_datos_reales_aunque_sean_de_otro_punto`: los datos del contexto eran correctos, pero la prueba esperaba estructuras de interfaz anteriores (`data-zona-toggle`). No se ha certificado que todos los controles y funciones anteriores tengan equivalentes en el rediseño; el hallazgo de paridad y la suite permanecen pendientes. Se actualizó otra expectativa de títulos para el tablero actual, conservando sus verificaciones de datos.

**Actualización de seguridad del entorno:** `SMOKE_TEST_SQLITE=True` tiene prioridad sobre `DATABASE_URL` para evitar que las pruebas hereden una conexión externa. El valor predeterminado de SQL Server en producción ahora exige validar el certificado (`TrustServerCertificate=no`); puede requerir instalar la CA válida y usar un nombre que coincida con el certificado. Pasaron cuatro pruebas de configuración, pero no se ha probado una conexión SQL Server real ni se han aplicado cambios en producción.

**Actualización de retorno y correo:** se validan también los destinos `next` y `siguiente` de los ajustes de cuenta; 16 pruebas combinadas de seguridad y configuración pasaron. Se eliminó `fail_silently=True` en envíos mediante el servicio de fondo y se verificó que un fallo SMTP se registra. Esto no sustituye la cola durable ni confirma entrega real. La ejecución aislada del módulo de Monitoreo detectó seis expectativas o funcionalidades pendientes de conciliar con el rediseño; por ello la suite y la paridad siguen sin certificarse.

**Regresión de respuestas y consulta acotada:** se recuperó la visualización de respuestas recientes de técnicos en el carrusel de zonas del observador y se limita la consulta por correos de las cuentas visibles antes de materializar comentarios. Pasaron tres pruebas enfocadas, incluida una de exclusión de comentarios ajenos y comparación de correos sin distinguir mayúsculas ni espacios. Falta medir rendimiento y verificar la consulta en SQL Server. La última suite completa iniciada no devolvió un resultado recuperable; no se considera aprobada.

**Validación posterior:** pasaron las 64 pruebas de `apps.tickets.test_monitoreo_zonas`. Se restablecieron las cuentas sin carpeta y sus enlaces en el panel del observador, y se corrigieron expectativas de interfaz que correspondían al diseño anterior. Las pruebas de seguridad de adjuntos ahora comprueban firma y terminación del PDF, sin que esto equivalga a un análisis completo del documento. Se añadió un timeout SMTP de 15 segundos; siguen pendientes la entrega durable y la validación de servicios reales.

**Media en Render:** se corrigió el fallback que no registraba rutas con `DEBUG=False`; ahora, cuando `DJANGO_SERVE_MEDIA=True`, solo se publica el directorio de avatares. La ruta de adjuntos continúa bloqueada y se sirve mediante la vista autorizada. Render activa ese fallback. Se probaron las rutas de resolución en un proceso aislado; falta validar el despliegue, Nginx, copias y accesos reales.

**Pruebas adicionales de adjuntos:** pasaron 11 pruebas de seguridad, incluidas la denegación a otra cuenta, el bloqueo de la URL directa aun para el dueño, la descarga autorizada y el tratamiento de SVG heredado con MIME manipulado. Siguen pendientes la comprobación frente al proxy real y la validación completa de PDFs.

**Alta de tickets y conflicto de edición:** pasaron seis pruebas de `apps.tickets.test_alta_ticket`. El editor informó que `templates/tickets/crear_ticket.html` tiene una versión sin guardar diferente al archivo en disco: debe compararse y fusionarse antes de guardar o desplegar, sin sobrescribir ninguna versión. La comprobación automática anterior corresponde al contenido guardado en disco, no al búfer del editor. Docker no pudo iniciar una comprobación adicional porque Windows informó falta de espacio en el archivo de paginación; la construcción de la imagen sigue pendiente.

**Cola durable — avance parcial:** se incorporaron el modelo cifrado `TareaDiferida`, la migración `tickets.0042`, una cola optativa para correos y seguimientos GLPI y el comando `procesar_tareas`. La reserva usa una actualización condicional y las tareas con entrega incierta quedan en revisión, sin reenvío automático. Se eliminará el contenido cifrado tras completar una entrega. Pasaron siete pruebas de la cola y 25 pruebas combinadas de cola, adjuntos y configuración; `makemigrations --check --dry-run` no detectó diferencias. No se ha aplicado la migración a una base real ni levantado un worker; la opción `DOGGER_FONDO_DURABLE` permanece desactivada por defecto, por lo que el riesgo de hilos daemon sigue vigente en instalaciones que no la activen.

Para ensayar el worker en un entorno aislado: configurar una `DOGGER_FERNET_KEY` válida y estable, aplicar las migraciones de prueba, arrancar `python manage.py procesar_tareas --loop` con supervisión y, solo con el worker verificado, activar `DOGGER_FONDO_DURABLE=True` y reiniciar los procesos web. `python manage.py procesar_tareas --estado` muestra contadores y reservas antiguas sin datos de mensajes. Ante una entrega incierta se requiere reconciliar con el destino antes de `--reintentar ID --confirmar`; una reserva estancada se marca para revisión con `--marcar-estancada ID --confirmar` después de detener el worker implicado. El sistema no garantiza entrega exactamente una vez ni reintenta automáticamente resultados ambiguos. Es necesario ensayar caídas, duplicados, alertas, retención, expiración de códigos y recuperación de la clave en el motor y la plataforma reales antes de activar la opción.

## Estado de remediación — actualización

La sección siguiente registra el avance sobre los 15 hallazgos originales. «Parcial» cuenta como pendiente para el estado final: un cambio local no certifica su aplicación ni la infraestructura real. Los diagnósticos originales se conservan más abajo como histórico.

| Nº | Hallazgo | Estado | Corrección y validación / trabajo restante |
|---:|---|---|---|
| 1 | Adjuntos publicados por media | Parcial | Se bloqueó `/media/adjuntos/` en los dos archivos Nginx y en las rutas Django; se probó el bloqueo Django. Pendiente desplegar y comprobar el proxy real, otras configuraciones de media y autorización entre usuarios. Avatares siguen siendo públicos. |
| 2 | JSON con `safe` | Resuelto | Cuatro inserciones sustituidas por `secure_json_script`, que usa `json_script`; prueba con cierre `</script>` aprobada. También se sustituyó una inserción de búsqueda mediante `innerHTML` por `textContent` en reportes. No implica que toda la aplicación esté libre de XSS. |
| 3 | Validación de adjuntos | Parcial | Se verifican imágenes raster con Pillow, extensión y contenido; PDF exige firma y se normaliza el MIME. Las pruebas rechazan imágenes falsas, SVG y PDF sin firma. Falta validar PDF completo, límites de descompresión, contenido heredado, otras rutas y antivirus. |
| 4 | Filtros ANS con campo inexistente | Resuelto | Se filtran los tickets por el plazo real calculado después de aplicar alcance del técnico. Pruebas para ambos filtros y aislamiento entre técnicos aprobadas. El cálculo en Python debe medirse con volumen real. |
| 5 | Migraciones | Parcial | `makemigrations --check --dry-run` sin diferencias y migraciones aplicadas a la base efímera de pruebas. Las migraciones 0020–0024 figuraban pendientes en SQLite de smoke; no se han consultado ni aplicado en producción, ni probado SQL Server. |
| 6 | Tareas asíncronas sin persistencia | Parcial | Existe una cola cifrada optativa con worker y recuperación manual de resultados inciertos, validada en SQLite. Está desactivada por defecto; faltan worker supervisado, despliegue, monitorización y pruebas en SQL Server/Render/Docker. No se ha certificado entrega exactamente una vez. |
| 7 | HTTPS, cookies y HSTS | Parcial | HSTS activado por defecto en producción, sin incluir subdominios ni preload salvo configuración explícita; Docker ya no desactiva HTTPS. `check --deploy` con parámetros simulados dejó W005 y W021 por subdominios/preload. Faltan comprobar proxy, hosts, orígenes, certificados y cookies reales. |
| 8 | Fallos de collectstatic silenciados | Parcial | `entrypoint.sh` falla si `collectstatic` falla y se retiró la ejecución tolerante del build. Falta construir/arrancar la imagen y comprobar manifiesto y archivos con WhiteNoise/Nginx reales. |
| 9 | SMTP silenciosamente en consola | Parcial | En producción, SMTP sin credenciales o backends de consola/dummy/archivo causan error de configuración; dos pruebas de arranque aprobadas. Falta probar entrega, TLS y recuperación de contraseña con el servidor real. |
| 10 | Redirecciones abiertas | Parcial | Validación de retorno añadida a rutas examinadas de observador, monitoreo y acciones de tickets; pruebas de URLs externas aprobadas. Falta comprobar todos los flujos y rutas de la aplicación. |
| 11 | Selector duplicado | Parcial | La búsqueda del selector ahora se hace en el mismo panel donde se inserta. Falta prueba funcional de reapertura y cambio de cuenta en navegador. |
| 12 | Diferencias observador/administrador | Parcial | Se añadieron búsqueda, filtros y paginación local de puntos, enlaces y respuestas de técnicos; pasaron 64 pruebas del módulo de Monitoreo. La ficha sigue usando tickets recientes limitados; faltan historial paginado autorizado, paridad completa y pruebas de navegador. |
| 13 | Consultas lentas | Pendiente | No se han medido carga, planes de ejecución, consultas ni índices en el motor y volumen de producción. |
| 14 | Dependencias y entorno | Pendiente | No se fijaron dependencias ni se realizó SCA; falta probar SQL Server, Docker y Render con sus servicios y backups reales. |
| 15 | Código duplicado y pruebas obsoletas | Parcial | Se actualizaron expectativas de fichas y permisos retirados; se corrigió un error en la página 500 sin usuario. Falta completar la suite y unificar componentes duplicados. |

### Estado actual

- **Resueltos:** 2/15.
- **Pendientes o parcialmente resueltos:** 13/15.
- **Bloqueantes de despliegue:** al menos 4 grupos: protección efectiva de media/archivos, migraciones y respaldos, entrega durable de tareas, y validación de configuración/servicios reales y suite completa.
- **Riesgo residual:** Alto.
- **Apto para producción:** No.

Las pruebas enfocadas ejecutadas tras los cambios incluyeron JSON, adjuntos, ANS, redirecciones, SMTP, página 500 y dos pruebas de monitoreo: 13 aprobadas con SQLite de prueba. Una ejecución previa de la suite completa con `--failfast` detectó un fallo en la página 500 y otra una expectativa obsoleta de reapertura; se corrigieron y se requiere volver a ejecutar la suite completa. No se han cambiado datos de producción ni aplicado migraciones reales.

Efectos secundarios: el arranque de producción ahora falla si falta SMTP válido; la base PostgreSQL de Compose exige contraseña explícita; `collectstatic` puede detener el arranque; validar imágenes puede rechazar archivos inválidos antes aceptados; HSTS exige que HTTPS esté operativo antes de desplegar. La configuración Nginx debe instalarse realmente en el proxy para proteger URLs directas.

Fecha de revisión: 31/10/2026. Resultado: **no recomendar publicación hasta resolver y validar los hallazgos críticos y altos**.

## Alcance y límites

Se inspeccionaron configuraciones Django, Docker y Nginx, autenticación, adjuntos, webhook, contadores, vistas de monitoreo, plantillas y consultas. Se ejecutaron comprobaciones con SQLite aislada y pruebas seleccionadas. No se realizó pentest, auditoría completa de todas las rutas, pruebas en navegador, medición de carga, análisis de dependencias contra vulnerabilidades conocidas ni validación en el entorno real de producción. Por ello, esta revisión no garantiza ausencia de vulnerabilidades.

No se imprimieron secretos ni se modificaron la base de datos de producción o la aplicación. La copia de trabajo tenía cambios previos y archivos sin seguimiento; el informe evalúa ese estado, no una versión publicada.

## Hallazgos

### 1. Crítico — Los adjuntos pueden quedar accesibles por URL directa

- **Archivos:** `nginx.conf:35`, `nginx.https.conf:91`, `apps/tickets/views.py:5245`.
- **Evidencia:** Nginx sirve `/media/` directamente desde el directorio de archivos; la vista `ver_adjunto` sí comprueba usuario, rol y pertenencia al ticket, pero una petición directa a la ubicación de media no pasa por esa vista.
- **Consecuencia:** quien conozca o consiga la URL de un archivo podría acceder a información de tickets sin la autorización de la aplicación. Confirmar en el despliegue real con dos cuentas y sin sesión; no asumir que nombres de archivo ocultos proporcionan seguridad.
- **Recomendación:** separar adjuntos privados de avatares y demás media pública, almacenar adjuntos fuera del directorio publicado y entregar únicamente mediante la vista autorizada o `X-Accel-Redirect` a una ubicación Nginx `internal`. Bloquear el acceso directo y probar autorización cruzada.

### 2. Alto — JSON insertado en `<script>` con `safe`

- **Archivos:** `templates/tickets/crear_ticket.html:115`, `templates/tickets/mi_panel.html:685`, `templates/tickets/_dash_widgets.html:193`, `apps/tickets/views.py:3704`.
- **Evidencia:** se incrustan valores serializados con `json.dumps` y `|safe` dentro de elementos `script`; los nombres de categorías, técnicos u otras cadenas pueden contener secuencias de cierre HTML. `json.dumps` no escapa por sí solo `</script>`.
- **Consecuencia:** riesgo de XSS almacenado si un campo editable llega a esas estructuras y el navegador interpreta un cierre de script. La explotabilidad concreta depende de quién pueda editar el campo y del contenido de cada JSON.
- **Recomendación:** usar `json_script` de Django y analizar `textContent` desde JavaScript. Ejemplo: `{{ datos|json_script:"datos-panel" }}`; entregar una estructura Python, no una cadena JSON ya serializada. Añadir prueba con `</script>` y texto HTML.

### 3. Alto — Validación de adjuntos basada en MIME del cliente

- **Archivos:** `apps/tickets/forms.py:161`, `apps/tickets/views.py:5419`, `apps/tickets/views.py:5278`.
- **Evidencia:** la validación utiliza `content_type` proporcionado por el cliente; una ruta AJAX admite cualquier MIME que comience por `image/`. La entrega inline también depende del MIME almacenado.
- **Consecuencia:** un archivo puede declarar un tipo distinto de su contenido; combinado con publicación directa de media puede facilitar entrega de contenido malicioso o evasión de restricciones.
- **Recomendación:** comprobar firma y contenido real, decodificar imágenes con Pillow, limitar extensiones y tamaño, impedir HTML/SVG inline y aplicar `Content-Disposition: attachment` a tipos no verificados. Evaluar antivirus y almacenamiento privado.

### 4. Alto — Filtro ANS consulta una propiedad como campo ORM

- **Archivos:** `apps/tickets/views.py:5800`, `apps/tickets/models.py:347`.
- **Evidencia:** los filtros `vencen-hoy` y `vencidas` usan `fecha_limite_ans__...`, pero `fecha_limite_ans` es una propiedad de Python, no un campo de modelo ni una anotación en esa consulta.
- **Consecuencia:** al seleccionar esos filtros, Django puede lanzar `FieldError` y producir una respuesta 500.
- **Recomendación:** reutilizar un cálculo ANS compatible con la base de datos, o filtrar un conjunto acotado en Python antes de paginar. Cubrir ambos filtros con pruebas en cada motor soportado. No convertir la propiedad a SQL suponiendo que todas las prioridades comparten el mismo plazo.

### 5. Alto — Cambios de base de datos pendientes y despliegue no reproducible

- **Archivos:** `apps/accounts/migrations/0020_usuario_rol_base.py` a `0024_usuario_horario_atencion.py`, `entrypoint.sh:6`.
- **Evidencia:** `showmigrations accounts`, contra la SQLite local de smoke test, mostró 0020–0024 pendientes. El árbol contiene cambios y archivos nuevos sin seguimiento, incluida la migración 0024. No se comprobó el estado de la base de producción.
- **Consecuencia:** código y esquema pueden no coincidir, generando errores de columnas y fallos de arranque. La migración 0024 no estará en una imagen construida desde un commit que no la incluya.
- **Recomendación:** revisar e incluir los cambios aprobados en el artefacto; hacer backup comprobado; inspeccionar `showmigrations` contra el destino real sin publicar credenciales; ensayar y aplicar migraciones mediante el procedimiento de despliegue, con plan de reversión.

### 6. Alto — Tareas asíncronas sin entrega garantizada

- **Archivos:** `apps/tickets/services/fondo.py:49`, `config/settings.py:232`, `apps/tickets/services/glpi_client.py:959`.
- **Evidencia:** envíos se ejecutan en hilos daemon del proceso web; no hay una cola persistente en esa implementación.
- **Consecuencia:** reinicios, despliegues o caída del worker pueden perder sincronizaciones y correos; varios procesos pueden dificultar el seguimiento y la repetición segura.
- **Recomendación:** cola persistente con trabajos idempotentes, reintentos limitados, estado de entrega, alertas y reconciliación GLPI. Registrar tareas después de confirmar transacciones y probar caída/reinicio del worker.

### 7. Alto — Cookies, HTTPS y secretos dependen de la configuración efectiva

- **Archivos:** `config/settings.py:250`, `.env.example:17`, `Dockerfile:27`, `docker-compose.yml:16`, `nginx.conf:15`.
- **Evidencia:** la configuración permite desactivar cookies seguras y redirección; Docker desactiva el redirect, y Compose contiene una contraseña de ejemplo para PostgreSQL. `check --deploy` con el entorno local cargado produjo advertencias W004, W008, W012, W016, W018 y W019. Con un perfil simulado explícito de producción y cookies/redirect seguros quedó W004 (HSTS).
- **Consecuencia:** una configuración incorrecta podría transmitir sesiones por HTTP o publicar el servicio en modo debug. Las advertencias locales no prueban cómo está configurado el servidor final.
- **Recomendación:** exigir secretos únicos y largos, `DEBUG=False`, cookies seguras, hosts y orígenes exactos; forzar HTTPS en el proxy o aplicación, aislar la aplicación tras el proxy y configurar HSTS solo después de verificar HTTPS en todos los dominios y subdominios. Eliminar contraseña por defecto en producción.

### 8. Alto — Los fallos de estáticos se ignoran en Docker

- **Archivos:** `Dockerfile:31`, `entrypoint.sh:9`.
- **Evidencia:** `collectstatic --noinput || true` permite continuar aunque falle; el build no garantiza que exista `DJANGO_SECRET_KEY` cuando Django se inicializa.
- **Consecuencia:** una imagen puede construirse o arrancar sin manifiesto o con activos incompletos/antiguos, con páginas rotas o archivos 404.
- **Recomendación:** hacer que `collectstatic` falle el build o el despliegue, usar configuración de build segura y no secreta cuando sea necesario, verificar el manifiesto y probar recursos con `DEBUG=False`.

### 9. Alto — Recuperación de contraseña puede no enviar correo

- **Archivo:** `config/settings.py:302`.
- **Evidencia:** si faltan credenciales SMTP, se usa automáticamente el backend de consola, incluso fuera del modo de prueba.
- **Consecuencia:** la aplicación puede anunciar el envío sin entregar el mensaje al usuario; además los correos quedarían en logs del proceso.
- **Recomendación:** fallar explícitamente o generar una alerta crítica si falta SMTP en producción; verificar entrega real, remitente y expiración de enlaces sin publicar contenido sensible.

### 10. Medio — Redirecciones de retorno sin validación

- **Archivo:** `apps/tickets/views_observador.py:965`, `:999`, `:2453`.
- **Evidencia:** varias acciones usan `redirect(request.POST.get("volver") or ...)` con una dirección suministrada por el cliente.
- **Consecuencia:** un atacante que consiga inducir un POST autenticado podría redirigir al usuario hacia un sitio externo; depende del flujo y protecciones CSRF.
- **Recomendación:** aceptar solo rutas locales con `url_has_allowed_host_and_scheme`, restringir hosts/esquema y usar una ruta fija como alternativa.

### 11. Medio — Selector de período duplicado en ficha

- **Archivo:** `templates/tickets/monitoreo_admin.html:1221`.
- **Evidencia:** el selector se busca dentro de `chartContainer` pero se inserta en el `h4` de la sección. Al volver a abrir la ficha la búsqueda no encuentra el selector anterior y puede agregar otro.
- **Consecuencia:** interfaz duplicada, controles obsoletos y manejadores inconsistentes.
- **Recomendación:** buscar e insertar en el mismo contenedor o declarar el selector una sola vez en la plantilla; limpiar o reemplazar el manejador al cambiar de cuenta. Probar abrir/cerrar varias fichas y cambiar período.

### 12. Medio — La vista del observador no equivale funcionalmente a la administrativa

- **Archivo:** `templates/observador/_paneles.html`, `apps/tickets/views_observador.py:1551`.
- **Evidencia:** el modal añadido al observador tiene búsqueda, pero carece de los filtros y paginación del administrador; la serie de tickets se construye a partir de recientes limitados.
- **Consecuencia:** el usuario puede no encontrar registros históricos y los dos roles ven experiencias distintas.
- **Recomendación:** compartir componentes de presentación sin ampliar permisos y proporcionar endpoint paginado autorizado para el observador, con filtros, pruebas de acceso entre zonas y valores reales.

### 13. Medio — Consultas y series que escalan con el volumen

- **Archivos:** `apps/tickets/views.py:966`, `apps/tickets/views_monitoreo.py:589`, `apps/tickets/views.py:444`.
- **Evidencia:** la actividad del punto recorre tickets propios para calcular vencimientos; el monitoreo agrega consultas y procesa registros y tickets para todas las zonas; el dashboard materializa conjuntos para cálculos en Python.
- **Consecuencia:** a mayor número de tickets y usuarios puede crecer la latencia, memoria y número de consultas, especialmente con múltiples workers.
- **Recomendación:** medir consultas por vista y `EXPLAIN` en la base real, limitar y agregar en base de datos cuando sea correcto, evitar recorridos repetidos y añadir índices según filtros y planes medidos. No recomendar índices específicos sin planes y cardinalidades reales.

### 14. Medio — Verificación insuficiente de dependencias y entorno

- **Archivos:** `requirements.txt`, `Dockerfile`, `render.yaml`, `build.sh`.
- **Evidencia:** la mayoría de dependencias tienen límites inferiores pero no versiones fijadas; SQL Server y su driver no se instalan en la imagen Linux por defecto. Render usa disco para media, pero no se ha verificado el servicio de esos archivos ni respaldos.
- **Consecuencia:** builds no reproducibles, incompatibilidades por actualización indirecta o fallos al usar un motor no preparado; pérdida de adjuntos si el almacenamiento no es persistente o no se respalda.
- **Recomendación:** generar un archivo bloqueado con hashes, ejecutar `pip-audit`/SCA en CI, construir y probar la imagen con el motor real, verificar volúmenes, restauración y rutas privadas de media. La presencia de una dependencia no demuestra por sí sola una vulnerabilidad concreta.

### 15. Bajo — Código duplicado y pruebas obsoletas

- **Archivos:** `templates/tickets/monitoreo_admin.html`, `templates/observador/_paneles.html`, `static/css/dogger-theme.css`, `apps/tickets/test_monitoreo_zonas.py:85`.
- **Evidencia:** hay implementaciones separadas de modales de puntos y reglas CSS acumuladas para las mismas tarjetas. La prueba `test_ve_zonas_agrupadas_por_supervisor` falla porque espera que el ojo abra otra pestaña, un comportamiento sustituido por el modal.
- **Consecuencia:** cambios visuales pueden divergir entre roles y pruebas desactualizadas impiden identificar regresiones reales.
- **Recomendación:** extraer componentes compartidos con datos y permisos explícitos; actualizar la prueba para el comportamiento solicitado y añadir pruebas de interacción, teclado, responsive y cierre de modales. No borrar pruebas solo para hacer pasar CI.

## Código recomendado para dos correcciones

```python
# Validar un destino de retorno antes de redirigir.
from django.utils.http import url_has_allowed_host_and_scheme

destino = request.POST.get("volver", "")
if not url_has_allowed_host_and_scheme(
    destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
):
    destino = reverse("tickets:obs_mi_lista")
return redirect(destino)
```

```django
{# Pasar una estructura Python a la plantilla, no JSON ya serializado. #}
{{ datos_grafica|json_script:"datos-grafica" }}
```

## Validaciones ejecutadas

- `manage.py test apps.accounts.test_seguridad apps.tickets.test_webhook apps.tickets.test_resolucion_contadores apps.tickets.test_actividad_punto`: **9 pruebas aprobadas** con SQLite de prueba.
- `manage.py check --deploy`: seis advertencias con el entorno local; con un perfil de producción simulado y HTTPS/cookies seguras quedó una advertencia HSTS. No certifica la configuración del servidor real.
- `manage.py showmigrations accounts`: en `smoketest.sqlite3` aparecen pendientes 0020–0024; no se consultó producción.
- En una ejecución previa, `test_ve_zonas_agrupadas_por_supervisor` falló por exigir `target="_blank"`; otra prueba de ficha antigua esperaba la clase `corp-kpis`. Requieren revisión frente al comportamiento actual.
- No se ejecutó la suite completa, análisis SCA, escáner web, pruebas de carga, migración real ni comprobaciones visuales de escritorio/móvil.

## Lista de verificación antes de publicar

- [ ] Bloquear acceso directo a adjuntos privados y probar con usuario ajeno y sin sesión.
- [ ] Sustituir JSON `|safe` en scripts y probar cadenas maliciosas controladas.
- [ ] Verificar archivos subidos por contenido, tamaño y tipo; comprobar descarga segura.
- [ ] Corregir filtros ANS y probarlos con tickets de distintas prioridades.
- [ ] Revisar permisos por rol y por objeto en todos los endpoints, exportaciones y adjuntos.
- [ ] Asegurar webhook GLPI con secreto independiente, TLS y pruebas de rechazo; verificar sincronización y reintentos.
- [ ] Revisar redirecciones, CSRF, XSS y carga de archivos con pruebas automatizadas.
- [ ] Fijar dependencias y ejecutar análisis de vulnerabilidades con base de datos actualizada.
- [ ] Revisar `DEBUG`, secreto, hosts, CSRF, cookies, HTTPS, proxy confiable y HSTS para el dominio real.
- [ ] Exigir contraseñas de base de datos y credenciales SMTP sin valores de ejemplo.
- [ ] Eliminar tolerancia silenciosa a fallos de estáticos y validar manifiesto con `DEBUG=False`.
- [ ] Incluir todas las migraciones aprobadas; hacer backup y probar restauración y migración en copia.
- [ ] Confirmar persistencia y respaldo de base de datos y adjuntos, con restauración ensayada.
- [ ] Probar creación, asignación, resolución, cierre directo, permisos, papelera, búsquedas y exportaciones.
- [ ] Validar contadores y filtros por rol, incluyendo resuelto+cierre y cierre directo.
- [ ] Revisar modales, filtros, gráficos, paginación, teclado, foco, responsive y navegadores soportados.
- [ ] Ejecutar suite completa y corregir o actualizar expectativas obsoletas con revisión funcional.
- [ ] Medir consultas, tiempos y memoria con volumen representativo, y revisar planes e índices.
- [ ] Configurar logs sin secretos, métricas, alertas, health checks, copias y procedimiento de respuesta.
- [ ] Definir despliegue, rollback, responsables y verificación posterior a la publicación.
