from django.core.management.base import BaseCommand

from apps.tickets.models import Categoria
from apps.tickets.services.glpi_client import GlpiClient, GlpiError


class Command(BaseCommand):
    help = (
        "Crea en GLPI las categorías ItilCategory que faltan y vincula "
        "el id de GLPI en cada Categoria de Dogger."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo muestra qué haría sin modificar nada.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        client = GlpiClient()
        if not client.available:
            self.stderr.write(self.style.ERROR("GLPI no está configurado o deshabilitado."))
            return

        client.init_session()
        try:
            cats_glpi = client.list_itil_categories()

            # Index por nombre (normalizado) para búsqueda rápida
            glpi_por_nombre = {}
            for c in cats_glpi:
                glpi_por_nombre[c["name"].strip().lower()] = c["id"]

            pendientes = Categoria.objects.filter(glpi_category_id__isnull=True)
            self.stdout.write(f"Categorías Dogger sin mapeo: {pendientes.count()}")
            self.stdout.write(f"Categorías GLPI existentes: {len(cats_glpi)}")

            creados = vinculados = 0

            for cat in pendientes:
                clave = cat.nombre.strip().lower()
                glpi_id = glpi_por_nombre.get(clave)

                if glpi_id:
                    # Ya existe en GLPI con el mismo nombre: vincular
                    if dry_run:
                        self.stdout.write(f"  [DRY] Vincular {cat.nombre} → GLPI #{glpi_id}")
                    else:
                        cat.glpi_category_id = glpi_id
                        cat.save(update_fields=["glpi_category_id"])
                        vinculados += 1
                        self.stdout.write(f"  [VINCULADO] {cat.nombre} → GLPI #{glpi_id}")
                else:
                    # No existe: crear en GLPI
                    if dry_run:
                        self.stdout.write(f"  [DRY] Crear {cat.nombre} en GLPI")
                    else:
                        try:
                            new_id = client.create_itil_category(cat.nombre)
                            cat.glpi_category_id = new_id
                            cat.save(update_fields=["glpi_category_id"])
                            glpi_por_nombre[clave] = new_id
                            creados += 1
                            self.stdout.write(f"  [CREADO] {cat.nombre} → GLPI #{new_id}")
                        except GlpiError as exc:
                            self.stderr.write(f"  [FALLO] {cat.nombre}: {exc}")
        finally:
            client.kill_session()

        resumen = f"Creados: {creados} | Vinculados: {vinculados} | Pendientes: {Categoria.objects.filter(glpi_category_id__isnull=True).count()}"
        self.stdout.write(self.style.SUCCESS(resumen))
