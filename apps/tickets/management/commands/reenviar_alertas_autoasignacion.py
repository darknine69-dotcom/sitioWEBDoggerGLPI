from django.core.management.base import BaseCommand

from apps.notificaciones.models import AlertaOperativa
from apps.tickets.models import DecisionAutoasignacion
from apps.tickets.services.autoasignacion_transaccional import _avisar_administradores


class Command(BaseCommand):
    help = "Reintenta idempotentemente las alertas abiertas de autoasignación."

    def handle(self, *args, **options):
        alertas = AlertaOperativa.objects.filter(
            tipo="asignacion_pendiente", estado=AlertaOperativa.Estado.ABIERTA,
            ticket__isnull=False, ticket__tecnico_asignado__isnull=True,
        ).order_by("pk")
        procesadas = 0
        for alerta in alertas.iterator():
            decision = DecisionAutoasignacion.objects.filter(ticket_id=alerta.ticket_id).order_by("-fecha", "-pk").first()
            if decision and decision.motivo in ("sin_candidatos", "capacidad_insuficiente"):
                _avisar_administradores(alerta.ticket_id, decision.motivo)
                procesadas += 1
        self.stdout.write(f"Alertas procesadas: {procesadas}; consulte el registro ante errores de entrega.")
