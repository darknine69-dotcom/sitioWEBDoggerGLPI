#!/bin/sh
# Ejecutar desde Cron Jobs después de configurar las variables de Django.
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(dirname -- "$SCRIPT_DIR")
if [ -z "${DOGGER_PYTHON:-}" ] || [ ! -x "$DOGGER_PYTHON" ]; then
    echo 'Configure DOGGER_PYTHON con la ruta del intérprete del entorno virtual.' >&2
    exit 1
fi
cd "$PROJECT_DIR"
exec "$DOGGER_PYTHON" manage.py enviar_resumen_semanal --enviar
