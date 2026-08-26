from django.core.management.base import BaseCommand

from apps.tickets.models import Ticket
from apps.tickets.services.glpi_client import (
    GlpiError,
    sync_adjuntos_to_glpi,
    sync_ticket_to_glpi,
)


class Command(BaseCommand):
    help = (
        "Reintenta la sincronización con GLPI: crea los tickets que aún no "
        "tienen glpi_id y sube los adjuntos pendientes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limite",
            type=int,
            default=50,
            help="Máximo de tickets a procesar por ejecución (default 50).",
        )

    def handle(self, *args, **options):
        limite = options["limite"]

        pendientes = Ticket.objects.filter(glpi_id__isnull=True).order_by("fecha_creacion")[:limite]
        creados = fallidos = 0
        for ticket in pendientes:
            try:
                glpi_id = sync_ticket_to_glpi(ticket)
            except GlpiError as exc:
                fallidos += 1
                self.stderr.write(f"[FALLO] {ticket.codigo}: {exc}")
                continue
            if glpi_id:
                creados += 1
                self.stdout.write(f"[OK] {ticket.codigo} → GLPI #{glpi_id}")
                try:
                    subidos = sync_adjuntos_to_glpi(ticket)
                    if subidos:
                        self.stdout.write(f"     └ {subidos} adjunto(s) subido(s)")
                except GlpiError as exc:
                    self.stderr.write(f"     └ adjuntos pendientes: {exc}")

        con_glpi = Ticket.objects.exclude(glpi_id__isnull=True)
        adjuntos_pendientes = sum(
            t.adjuntos.filter(sincronizado_glpi=False).count() for t in con_glpi
        )

        resumen = [
            f"Tickets sincronizados ahora: {creados}",
            f"Tickets con fallo: {fallidos}",
            f"Aún sin glpi_id: {Ticket.objects.filter(glpi_id__isnull=True).count()}",
            f"Adjuntos pendientes de subir: {adjuntos_pendientes}",
        ]
        self.stdout.write(self.style.SUCCESS(" | ".join(resumen)))
