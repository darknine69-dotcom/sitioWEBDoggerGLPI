from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.notificaciones.resumen_semanal import BOGOTA, enviar_resumen


class Command(BaseCommand):
    help = "Previsualiza o envía los resúmenes semanales optativos."

    def add_arguments(self, parser):
        parser.add_argument("--enviar", action="store_true", help="Autoriza el envío real; sin esta opción solo cuenta candidatos.")

    def handle(self, *args, **options):
        ahora = timezone.now()
        local = timezone.localtime(ahora, BOGOTA)
        if options["enviar"] and (local.weekday() != 0 or local.hour < 8):
            raise CommandError("El envío solo está permitido los lunes desde las 08:00, hora de Bogotá.")
        usuarios = get_user_model().objects.filter(activo=True, is_active=True).exclude(email="")
        candidatos = [u.pk for u in usuarios.only("pk", "preferencias_notificaciones")
                      if (u.preferencias_notificaciones or {}).get("correo_resumen") is True]
        if not options["enviar"]:
            self.stdout.write(f"Previsualización: {len(candidatos)} cuenta(s) suscrita(s); no se enviaron correos.")
            return
        resultados = [enviar_resumen(pk, ahora) for pk in candidatos]
        self.stdout.write(f"Enviados: {resultados.count('enviado')}; requieren revisión: {resultados.count('revisar')}; ya procesados: {resultados.count('ya_procesado')}.")
        if "revisar" in resultados:
            raise CommandError("Hay envíos sin confirmación; revisar antes de cualquier reintento.")
