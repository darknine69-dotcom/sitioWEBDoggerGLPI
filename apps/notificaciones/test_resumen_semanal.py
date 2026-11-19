from datetime import datetime
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.notificaciones.resumen_semanal import enviar_resumen, periodo_semanal
from apps.tickets.models import Ticket


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", DEFAULT_FROM_EMAIL="test@example.invalid")
class ResumenSemanalTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(email="uno@example.com", nombre="Uno", password="clave", rol="usuario")
        self.ahora = datetime(2026, 11, 9, 8, 0, tzinfo=ZoneInfo("America/Bogota"))

    def activar(self):
        self.usuario.preferencias_notificaciones = {"correo_resumen": True}
        self.usuario.save(update_fields=["preferencias_notificaciones"])

    def test_periodo_y_suscripcion_por_defecto(self):
        inicio, fin = periodo_semanal(self.ahora)
        self.assertEqual((str(inicio.date()), str(fin.date())), ("2026-11-02", "2026-11-09"))
        self.assertEqual(enviar_resumen(self.usuario.pk, self.ahora), "no_suscrito")
        self.assertEqual(len(mail.outbox), 0)

    def test_resumen_se_guarda_y_no_se_duplica(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.post(reverse("accounts:preferencias_correo"), {"clave": "correo_resumen", "valor": "1"}).status_code, 200)
        ticket = Ticket.objects.create(titulo="Propio", descripcion="Prueba", solicitante_nombre="Uno", solicitante_email=self.usuario.email)
        Ticket.objects.filter(pk=ticket.pk).update(fecha_creacion=datetime(2026, 11, 3, 12, tzinfo=ZoneInfo("America/Bogota")))
        mail.outbox.clear()
        self.assertEqual(enviar_resumen(self.usuario.pk, self.ahora), "enviado")
        self.assertEqual(enviar_resumen(self.usuario.pk, self.ahora), "ya_procesado")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Tickets que solicitaste: 1", mail.outbox[0].body)

    @patch("apps.notificaciones.resumen_semanal.send_mail", side_effect=RuntimeError("SMTP"))
    def test_fallo_incierto_no_reintenta(self, enviar):
        self.activar()
        self.assertEqual(enviar_resumen(self.usuario.pk, self.ahora), "revisar")
        self.assertEqual(enviar_resumen(self.usuario.pk, self.ahora), "ya_procesado")
        enviar.assert_called_once()

    def test_comando_previsualiza_y_rechaza_fuera_del_horario(self):
        self.activar()
        salida = StringIO()
        call_command("enviar_resumen_semanal", stdout=salida)
        self.assertIn("1 cuenta(s)", salida.getvalue())
        self.assertEqual(len(mail.outbox), 0)
        with patch("apps.notificaciones.management.commands.enviar_resumen_semanal.timezone.now", return_value=self.ahora.replace(hour=7)):
            with self.assertRaises(CommandError):
                call_command("enviar_resumen_semanal", "--enviar")
