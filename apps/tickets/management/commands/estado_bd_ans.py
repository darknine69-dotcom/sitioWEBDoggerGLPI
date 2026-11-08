"""Diagnóstico de base ANS de solo lectura, sin mostrar datos de conexión."""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from pathlib import Path


class Command(BaseCommand):
    help = "Muestra motor, versión, entorno lógico y estado de migraciones sin revelar credenciales."

    def add_arguments(self, parser):
        parser.add_argument("--entorno", required=True, choices=["local", "pruebas", "produccion"])

    def handle(self, *args, **options):
        self.stdout.write("Entorno lógico declarado: " + options["entorno"])
        self.stdout.write("Motor: " + connection.vendor)
        try:
            if connection.vendor == "sqlite":
                nombre = str(connection.settings_dict.get("NAME") or "")
                if not nombre or nombre == ":memory:" or nombre.startswith("file:") or not Path(nombre).is_file():
                    raise CommandError("SQLite debe apuntar a un archivo existente; no se creará una base nueva.")
            connection.ensure_connection()
            version = connection.get_database_version()
            self.stdout.write("Conectividad: disponible")
            self.stdout.write("Versión: " + ".".join(str(x) for x in version))
            executor = MigrationExecutor(connection)
            pendientes = executor.migration_plan(executor.loader.graph.leaf_nodes())
            aplicadas = executor.loader.applied_migrations
            for nombre in ("0047_ticket_ans_categoria_original_and_more", "0048_ticket_ans_version_ajuste_ticketajusteans"):
                self.stdout.write(nombre + ": " + ("aplicada" if ("tickets", nombre) in aplicadas else "no aplicada"))
            self.stdout.write("Migraciones pendientes totales: " + str(len(pendientes)))
        except Exception:
            raise CommandError("No fue posible consultar conectividad, versión o migraciones; revise el entorno sin compartir credenciales.") from None
