from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.notificaciones.emails import _enviar


class ErrorCorreoTest(SimpleTestCase):
    @override_settings(EMAIL_HOST_USER="test@example.invalid", DOGGER_FONDO_ASINCRONO=False)
    def test_fallo_smtp_se_registra_y_no_se_ignora(self):
        with patch("apps.notificaciones.emails.send_mail", side_effect=OSError("fallo SMTP")) as enviar:
            with self.assertLogs("apps.notificaciones.emails", level="ERROR"):
                self.assertFalse(_enviar("Asunto", "Texto", "<p>Texto</p>", ["destino@example.invalid"]))
        self.assertFalse(enviar.call_args.kwargs["fail_silently"])
