from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings


class ComprobarCorreoTests(SimpleTestCase):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.invalid", EMAIL_PORT=587,
        EMAIL_HOST_USER="cuenta-secreta", EMAIL_HOST_PASSWORD="clave-secreta",
        DEFAULT_FROM_EMAIL="remitente@example.invalid", EMAIL_USE_TLS=True, EMAIL_USE_SSL=False,
    )
    def test_no_expone_credenciales_ni_afirma_conexion(self):
        salida = StringIO()
        call_command("comprobar_correo", stdout=salida)
        texto = salida.getvalue()
        self.assertIn("Backend SMTP: sí", texto)
        self.assertIn("no se han verificado autenticación ni entrega", texto)
        for secreto in ("cuenta-secreta", "clave-secreta", "smtp.example.invalid", "remitente@example.invalid"):
            self.assertNotIn(secreto, texto)
