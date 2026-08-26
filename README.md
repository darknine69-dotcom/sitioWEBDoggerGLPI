# Dogger HelpDesk — Django + SQL Server 2022 + GLPI (opcional)

Mesa de ayuda de **Productos Alimenticios Dogger S.A.S.** alineada a la infraestructura STATU QUO (SIESA, POS, Fortinet, Server Principal).

## Características

- Portal público: crear tickets, adjuntar capturas, consultar por código `HD-XXXX`
- Panel staff: dashboard, filtros, estados, asignación de técnico, comentarios
- BD normalizada en **SQL Server 2022**
- Sincronización **opcional** hacia **GLPI** (API REST)
- Categorías de negocio: SIESA, POS, red/firewall, servidores, integraciones

## Inicio rápido

```bash
cd dogger_django
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Editar .env (DB_* y DJANGO_SECRET_KEY)

python manage.py makemigrations accounts tickets
python manage.py migrate
python manage.py seed_categorias
python manage.py createsuperuser   # o shell create_user con rol=admin
python manage.py runserver
```

## Documentación

- **MANUAL.md** — operación, infraestructura Dogger, cómo hacer cambios, GLPI, smoke tests
- `.env.example` — variables de entorno

## Estructura

```
config/           settings, urls
apps/accounts/    Usuario + login
apps/tickets/     modelos, vistas, forms, services/glpi_client.py
templates/        portal, panel, consultar
static/css/       dogger-theme.css
media/adjuntos/   capturas
```

## GLPI

Por defecto `GLPI_ENABLED=False`. Cuando GLPI esté en la LAN:

```env
GLPI_ENABLED=True
GLPI_BASE_URL=http://glpi.dogger.local/apirest.php
GLPI_APP_TOKEN=...
GLPI_USER_TOKEN=...
```

Ver MANUAL.md sección 5.
