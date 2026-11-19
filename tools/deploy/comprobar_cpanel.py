"""Diagnóstico de solo lectura; no envía correos ni aplica migraciones."""
import importlib
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main():
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.staticfiles import finders
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from django.template.loader import get_template
    from apps.tickets.models import TareaDiferida

    print("Django:", django.get_version())
    print("Depuración desactivada:", not settings.DEBUG)
    print("Backend Graph seleccionado:", settings.EMAIL_BACKEND == "config.graph_email_backend.GraphEmailBackend")
    try:
        importlib.import_module("config.graph_email_backend")
        print("Backend Graph importable: sí")
    except Exception as exc:
        print("Backend Graph importable: no (", type(exc).__name__, ")", sep="")
    for nombre in ("MS_GRAPH_CLIENT_ID", "MS_GRAPH_TENANT_ID", "MS_GRAPH_CLIENT_SECRET", "MS_GRAPH_SENDER"):
        print(nombre + " configurada:", bool(os.environ.get(nombre)))
    print("Cola durable habilitada:", settings.DOGGER_FONDO_DURABLE)
    try:
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        print("Migraciones pendientes:", len(plan))
        for valor, etiqueta in TareaDiferida.Estado.choices:
            print("Cola", etiqueta + ":", TareaDiferida.objects.filter(estado=valor).count())
    except Exception as exc:
        print("Estado de base no disponible:", type(exc).__name__)
    try:
        get_template("notificaciones/emails/ticket_recibido_usuario.html")
        print("Plantilla de correo: disponible")
    except Exception as exc:
        print("Plantilla de correo:", type(exc).__name__)
    print("CSS principal localizado:", bool(finders.find("css/dogger-theme.css")))
    try:
        resultado = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=settings.BASE_DIR,
                                   capture_output=True, text=True, timeout=5, check=True)
        print("Commit local:", resultado.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        print("Commit local: no disponible (copia sin Git o comando ausente)")
    print("No se verificó entrega SMTP/Graph, integridad del respaldo ni concurrencia.")


if __name__ == "__main__":
    main()
