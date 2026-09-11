from django.core.management.base import BaseCommand

from apps.tickets.models import Ticket
from apps.tickets.services.glpi_client import (
    GlpiError,
    sync_adjuntos_to_glpi,
    sync_edicion_to_glpi,
)


class Command(BaseCommand):
    help = (
        "Re-sincroniza tickets que ya tienen glpi_id: actualiza contenido, "
        "prioridad, categoría, solicitante y técnico asignado en GLPI."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limite",
            type=int,
            default=0,
            help="Máximo de tickets a procesar (0 = todos).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo muestra qué tickets se actualizarían sin modificar nada.",
        )

    def handle(self, *args, **options):
        limite = options["limite"]
        dry_run = options["dry_run"]

        qs = Ticket.objects.filter(glpi_id__isnull=False).order_by("fecha_creacion")
        if limite:
            qs = qs[:limite]

        total = qs.count()
        self.stdout.write(f"Tickets con glpi_id para re-sincronizar: {total}")

        exitosos = fallidos = 0
        for ticket in qs:
            if dry_run:
                self.stdout.write(f"  [DRY-RUN] {ticket.codigo} → GLPI #{ticket.glpi_id}")
                continue
            try:
                sync_edicion_to_glpi(ticket)
                exitosos += 1
                self.stdout.write(f"  [OK] {ticket.codigo} → GLPI #{ticket.glpi_id}")
                try:
                    subidos = sync_adjuntos_to_glpi(ticket)
                    if subidos:
                        self.stdout.write(f"       └ {subidos} adjunto(s) subido(s)")
                except GlpiError as exc:
                    self.stderr.write(f"       └ adjuntos: {exc}")
            except GlpiError as exc:
                fallidos += 1
                self.stderr.write(f"  [FALLO] {ticket.codigo}: {exc}")

        resumen = f"Exitosos: {exitosos} | Fallidos: {fallidos} | Total: {total}"
        self.stdout.write(self.style.SUCCESS(resumen))
