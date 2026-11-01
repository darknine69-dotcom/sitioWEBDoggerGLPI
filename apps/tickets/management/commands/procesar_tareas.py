"""Procesa la cola durable mediante un worker supervisado."""
import time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.tickets.models import TareaDiferida
from apps.tickets.services.cola_durable import procesar_una, tareas_estancadas


class Command(BaseCommand):
    help = "Procesa tareas persistentes de correo y GLPI sin reenviar resultados inciertos."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Mantener el worker activo.")
        parser.add_argument("--intervalo", type=int, default=5, help="Segundos entre sondeos cuando no hay tareas.")
        parser.add_argument("--estado", action="store_true", help="Mostrar contadores sin datos sensibles.")
        parser.add_argument("--reintentar", type=int, metavar="ID", help="Reencolar una tarea revisada manualmente.")
        parser.add_argument("--marcar-estancada", type=int, metavar="ID", help="Marcar para revisión una tarea reservada hace más de 10 minutos.")
        parser.add_argument("--confirmar", action="store_true", help="Confirma que se verificó el destino antes de reintentar.")

    def handle(self, *args, **options):
        if options["estado"]:
            for estado, etiqueta in TareaDiferida.Estado.choices:
                self.stdout.write(f"{etiqueta}: {TareaDiferida.objects.filter(estado=estado).count()}")
            self.stdout.write(f"Reservadas hace más de 10 min: {tareas_estancadas().count()}")
            return
        if options["marcar_estancada"] is not None:
            if not options["confirmar"]:
                raise CommandError("Detén el worker implicado y usa --confirmar antes de marcarla.")
            actualizadas = tareas_estancadas().filter(pk=options["marcar_estancada"]).update(
                estado=TareaDiferida.Estado.REVISAR, ultimo_error="Reserva interrumpida", actualizado_en=timezone.now(),
            )
            if not actualizadas:
                raise CommandError("La tarea no existe o no lleva suficiente tiempo reservada.")
            self.stdout.write("Tarea marcada para revisar; no se reenviará automáticamente.")
            return
        if options["reintentar"] is not None:
            if not options["confirmar"]:
                raise CommandError("Verifica la entrega externa y usa --confirmar para evitar duplicados.")
            actualizadas = TareaDiferida.objects.filter(
                pk=options["reintentar"], estado__in=[TareaDiferida.Estado.REVISAR, TareaDiferida.Estado.FALLIDA]
            ).exclude(datos="").update(estado=TareaDiferida.Estado.PENDIENTE, disponible_en=timezone.now(), reservado_en=None, ultimo_error="", actualizado_en=timezone.now())
            if not actualizadas:
                raise CommandError("La tarea no existe o no está pendiente de revisión.")
            self.stdout.write("Tarea reencolada; puede volver a entregarse.")
            return
        intervalo = max(1, min(options["intervalo"], 60))
        while True:
            pk = procesar_una()
            if not options["loop"]:
                self.stdout.write(f"Tarea procesada: {pk}" if pk else "Sin tareas pendientes.")
                return
            if pk is None:
                time.sleep(intervalo)
