# Manual de operación y cambios — Dogger HelpDesk + GLPI

**Empresa:** Productos Alimenticios Dogger S.A.S.  
**Sede:** Calle 39 sur 26-09, Envigado, Antioquia, Colombia  
**Referencia de red:** diagrama STATU QUO (SIESA, POS, Fortinet, Server Principal, etc.)

Este documento explica cómo funciona el sistema, cómo encaja en la infraestructura Dogger y **cómo hacer cambios** sin romper el conjunto.

---

## 1. Qué es este sistema

| Capa | Tecnología | Rol |
|------|------------|-----|
| Portal + panel | Django 5 | Crear tickets, capturas, dashboard, staff |
| Base de datos | SQL Server 2022 | Persistencia local (Tickets, Usuarios…) |
| ITSM opcional | GLPI (API REST) | Sincronizar tickets al helpdesk corporativo |

El portal Dogger es la **cara amigable** (estilo comanda). GLPI es el **motor ITIL** cuando lo actives en la LAN.

---

## 2. Encaje en la infraestructura (STATU QUO)

Según el diagrama de red Dogger:

```
[Puntos de venta PC-P1 …]     [Oficinas / Admin]
         \                         /
          \    LAN Dogger         /
           \        |            /
      Fortinet 200E / WatchGuard
                    |
            Server Principal
           /        |         \
    SQL Server   Django/GLPI   SIESA ERP
    (Tickets)    (este app)    POS-FE / Web
```

**Recomendaciones de despliegue**

| Componente | Dónde instalarlo |
|------------|------------------|
| SQL Server (BD `Tickets`) | Server Principal o instancia dedicada |
| App Django | Server Principal, Terminal Server o VM interna |
| GLPI | Misma LAN (`glpi.dogger.local`), solo intranet |
| Acceso usuarios | HTTP(S) interno; no exponer SQL ni API GLPI a Internet |

**Categorías del catálogo** reflejan el diagrama:

- SIESA ERP / Web / Cloud  
- Puntos de venta (POS Hardware, POS-FE, Cajón, Impresoras)  
- Infraestructura (Fortinet, WatchGuard, Server Principal, Archivos, Correos, Backup…)  
- Integraciones (GenericTransfer, Web Service, Correos HUGE)  
- Soporte TI y Administrativo TI  

Para cambiar el catálogo: ver sección 6.

---

## 3. Roles

| Rol | Quién | Puede |
|-----|-------|--------|
| Público | Cualquier colaborador | Crear ticket + adjuntos, consultar por código HD-XXXX |
| `tecnico` | Sistemas | Panel, estados, adjuntos, comentarios, asignar |
| `admin` | Jefe sistemas | Igual + Django Admin (`/admin/`) |

El decorador `@staff_required` exige `user.es_staff_helpdesk` (rol admin o tecnico y activo).

---

## 4. Instalación inicial (checklist)

1. ODBC Driver 17/18 for SQL Server en el servidor de la app.  
2. Base `Tickets` creada en SQL Server 2022.  
3. `python -m venv .venv` → activar → `pip install -r requirements.txt`  
4. Copiar `.env.example` → `.env` y completar `DB_*`, `DJANGO_SECRET_KEY`.  
5. `python manage.py makemigrations accounts tickets`  
6. `python manage.py migrate`  
7. `python manage.py seed_categorias`  
8. Crear usuario staff:

```bash
python manage.py shell
```

```python
from apps.accounts.models import Usuario
Usuario.objects.create_user(
    email="sistemas@dogger.com.co",
    nombre="Sistemas Dogger",
    password="CambiaEstoYa",
    rol="admin",
    is_staff=True,
)
```

9. `python manage.py runserver 0.0.0.0:8000` (o IIS/gunicorn en producción).

**URLs**

| Ruta | Uso |
|------|-----|
| `/` | Portal público |
| `/consultar/` | Buscar HD-0001 |
| `/cuenta/login/` | Login staff |
| `/panel/` | Dashboard |
| `/panel/tickets/` | Lista y gestión |
| `/admin/` | Django Admin |

---

## 5. Activar sincronización GLPI

1. Instala GLPI en un host de la LAN (ej. detrás de Fortinet).  
2. En GLPI: *Configuración → General → API* → habilitar API, crear **App-Token** y **User-Token** de un usuario técnico.  
3. En `.env`:

```env
GLPI_ENABLED=True
GLPI_BASE_URL=http://glpi.dogger.local/apirest.php
GLPI_APP_TOKEN=...
GLPI_USER_TOKEN=...
```

4. (Opcional) En Django Admin, en cada **Categoría**, llena `glpi_category_id` con el ID de la categoría ITIL equivalente en GLPI.  
5. Al crear un ticket en el portal, si GLPI responde OK se guarda `ticket.glpi_id`; el solicitante se vincula buscando al usuario GLPI por correo y los adjuntos se suben con su nombre original.  
6. Al cambiar estado (abierto → en-progreso → resuelto → cerrado) se intenta actualizar el status en GLPI.  
7. Reintento manual de tickets que quedaron sin sincronizar:

```bash
python manage.py sync_glpi_pendientes          # procesa hasta 50
python manage.py sync_glpi_pendientes --limite 200
```

### 5.1 Reenvío, edición y asignación automática

- **Reenviar a GLPI**: botón "🔁 Reenviar/Actualizar en GLPI" en la vista del ticket
  (dueño o staff). Crea el ticket en GLPI si falta, sube adjuntos pendientes y
  refleja cambios. No duplica: si ya existe, actualiza.
- **Edición por el solicitante**: mientras el ticket está `abierto`, el dueño puede
  editarlo ("✏️ Editar ticket"). Si ya está en GLPI, los cambios se sincronizan.
- **Asignación automática**: en Django Admin, cada **Categoría** puede tener un
  *Técnico por defecto*; los tickets nuevos de esa categoría se le asignan solos
  (`asignacion_automatica=True`). Al cambiar de categoría en la edición se reasigna.
- **Reasignación manual**: panel staff → detalle del ticket → Asignar técnico
  (queda marcado como manual). Para que la asignación llegue a GLPI, guarda en
  Django Admin → Usuarios → campo **ID usuario GLPI** de cada técnico
  (búscalo en GLPI → Usuarios → ID).

Después de aplicar cambios de modelos: `python manage.py migrate`

**Código clave:** `apps/tickets/services/glpi_client.py`

Notas:
- La URL debe ser la **API clásica** (`/apirest.php`). Si se configura la nueva (`http://host/api.php/v1`), el cliente la convierte automáticamente.
- Si GLPI está caído, el ticket **igual se guarda** en SQL Server y el portal muestra un aviso; luego se recupera con `sync_glpi_pendientes`.

### 5.2 Interfaz del panel (rediseño)

- **Header rojo corporativo** con logo; barra de navegación fija según rol (usuario / técnico / administrador). El **Dashboard y Reportes solo los ve el administrador**.
- **Tickets (staff):** barra de filtros con búsqueda (código HD, título, solicitante), estado, prioridad, categoría, técnico + paginación. El botón Excel respeta los filtros activos.
- **Categorías:** vista compacta por grupo (plegable). Permite crear subcategorías (con técnico por defecto e ID GLPI opcional), editar en línea, desactivar/activar y eliminar (solo si no tiene tickets).
- **Usuarios (solo admin):** alta/edición de cuentas desde el panel, activar/desactivar y botón **“Importar de GLPI”**, que trae los técnicos creados en GLPI (las cuentas nuevas quedan inactivas hasta asignarles contraseña).
- **Reportes:** tarjetas por estado que abren un modal con los últimos tickets de ese estado; gráficas hechas con CSS puro (funcionan sin internet, sin Chart.js).
- **Portal público:** formulario “Reportar una incidencia” sin iniciar sesión; entrega código HD para seguimiento.
- Botones **← volver** en las vistas de detalle.

---

## 6. Cómo hacer cambios frecuentes

### 6.1 Agregar una categoría

**Opción A — Admin web**  
`/admin/` → Categorías → Añadir (grupo + nombre).

**Opción B — Seed**  
Edita la lista `CATEGORIAS` en:

`apps/tickets/management/commands/seed_categorias.py`

Luego:

```bash
python manage.py seed_categorias
```

### 6.2 Cambiar colores / marca

Archivo único: `static/css/dogger-theme.css`  
Variables al inicio (`--dogger-red`, `--dogger-black`, etc.).

### 6.3 Cambiar correo / WhatsApp de soporte

`.env`:

```env
DOGGER_CORREO=...
DOGGER_WHATSAPP=...
```

O `DOGGER` en `config/settings.py`.

### 6.4 Agregar un campo al ticket

1. Modelo: `apps/tickets/models.py` → clase `Ticket`  
2. `python manage.py makemigrations tickets && python manage.py migrate`  
3. Formulario: `apps/tickets/forms.py` → `TicketForm.Meta.fields`  
4. Plantillas: `templates/tickets/portal.html` y `detalle.html`  

### 6.5 Cambiar reglas de adjuntos

`settings.DOGGER["max_adjuntos"]` y `max_adjunto_mb`  
Tipos MIME: `ALLOWED_CONTENT_TYPES` en `forms.py`.

### 6.6 Mapeo de estados Dogger ↔ GLPI

En `glpi_client.py`:

```python
STATE_TO_GLPI_STATUS = {
    "abierto": 1,
    "en-progreso": 2,
    "resuelto": 5,
    "cerrado": 6,
}
```

Ajusta si tu instancia GLPI usa otra numeración.

### 6.7 Desactivar GLPI temporalmente

```env
GLPI_ENABLED=False
```

No requiere redeploy de código.

---

## 7. Modelo de datos (normalizado)

```
Usuarios ──< Tickets >── Categorias
              │              (glpi_category_id)
              ├── TicketAdjuntos
              ├── TicketComentarios
              └── glpi_id (FK lógica hacia GLPI)
```

Tablas SQL Server: `Usuarios`, `Categorias`, `Tickets`, `TicketAdjuntos`, `TicketComentarios`.

---

## 8. Validación rápida (smoke test)

Sin GLPI:

1. Abrir `/` → crear ticket con una captura.  
2. Debe aparecer código `HD-00xx` y el archivo en `media/adjuntos/HD-00xx/`.  
3. `/consultar/?codigo=HD-00xx` muestra estado.  
4. Login staff → `/panel/` contadores > 0.  
5. Abrir ticket → cambiar a “en progreso” → agregar comentario interno.  

Con GLPI (`GLPI_ENABLED=True`):

6. Tras crear ticket, en detalle debe verse **GLPI #N**.  
7. En GLPI, el ticket aparece con el texto del solicitante y código Dogger.

Errores típicos:

| Síntoma | Causa probable |
|---------|----------------|
| Error conexión BD | ODBC / `DB_HOST` / firewall local |
| Login no entra | Usuario inactivo o rol incorrecto |
| Adjunto no sube | Tipo MIME o tamaño > 8 MB |
| GLPI no sincroniza | Tokens, URL, o API deshabilitada en GLPI |

---

## 9. Producción (mínimo)

- `DJANGO_DEBUG=False`  
- `DJANGO_SECRET_KEY` fuerte  
- HTTPS interno (certificado en IIS/nginx)  
- No publicar `media/` ni SQL a Internet  
- Backups de BD `Tickets` + carpeta `media/adjuntos`  
- Usuario SQL con permisos solo sobre la base `Tickets`  

---

## 10. Archivos que más vas a tocar

| Archivo | Para qué |
|---------|----------|
| `config/settings.py` | BD, GLPI, DOGGER |
| `.env` | Secretos y flags |
| `apps/tickets/models.py` | Estructura de datos |
| `apps/tickets/views.py` | Lógica de pantallas |
| `apps/tickets/forms.py` | Validaciones de formularios |
| `apps/tickets/services/glpi_client.py` | Integración GLPI |
| `apps/tickets/management/commands/seed_categorias.py` | Catálogo |
| `static/css/dogger-theme.css` | Diseño |
| `templates/tickets/*` | HTML |

---

## 11. Roadmap sugerido (post go-live)

1. Notificaciones correo al cambiar estado (SMTP interno Dogger).  
2. SLA por prioridad (campo fecha límite).  
3. Plugin Formcreator en GLPI si el portal Django se retira.  
4. Inventario de PCs (PC-P1…) en GLPI enlazado al ticket.  
5. Consulta de ticket por correo del solicitante además del código.

---

*Documento generado para el proyecto Dogger HelpDesk Django + GLPI.  
Referencia de infraestructura: diagrama STATU QUO Dogger S.A.S.*
