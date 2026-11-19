"""Diagnóstico local de configuración; nunca abre conexión ni envía mensajes."""
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Comprueba la configuración de correo sin conectarse ni enviar mensajes."

    def handle(self, *args, **options):
        comprobaciones = {
            "Backend SMTP": settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend",
            "Servidor configurado": bool(settings.EMAIL_HOST),
            "Puerto válido": 1 <= settings.EMAIL_PORT <= 65535,
            "Remitente configurado": bool(settings.DEFAULT_FROM_EMAIL),
            "Usuario configurado": bool(settings.EMAIL_HOST_USER),
            "Contraseña configurada": bool(settings.EMAIL_HOST_PASSWORD),
            "Cifrado TLS o SSL": bool(settings.EMAIL_USE_TLS or settings.EMAIL_USE_SSL),
        }
        for nombre, correcto in comprobaciones.items():
            self.stdout.write(f"{nombre}: {'sí' if correcto else 'no'}")
        self.stdout.write("Sin conexión ni envío: no se han verificado autenticación ni entrega.")
