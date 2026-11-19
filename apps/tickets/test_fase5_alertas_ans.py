from datetime import timedelta
from unittest.mock import patch

from django.db.models import QuerySet
from django.test import TestCase
from django.utils import timezone

from apps.notificaciones.models import AlertaOperativa, Notificacion
from apps.tickets.ans_avisos import avisar, avisos_en_campana, por_vencer
from apps.tickets.models import Ticket


class AlertasANSVerificadasTests(TestCase):
    def setUp(self):
        self.ticket = Ticket.objects.create(
            titulo="Caso ANS", descripcion="Prueba", solicitante_nombre="Prueba",
            solicitante_email="prueba@example.invalid", prioridad=Ticket.Prioridad.MEDIA,
        )
        inicio = timezone.now() - timedelta(hours=13)
        QuerySet.update(Ticket.objects.filter(pk=self.ticket.pk),
                        fecha_creacion=inicio, ans_inicio_original=inicio,
                        ans_limite_original=inicio + timedelta(hours=12))
        self.ticket.refresh_from_db()

    def test_historico_desconocido_no_genera_alertas_definitivas(self):
        QuerySet.update(Ticket.objects.filter(pk=self.ticket.pk), ans_verificacion="desconocido")
        self.ticket.refresh_from_db()
        self.assertNotIn(self.ticket, por_vencer(solo_verificados=True))
        self.assertEqual(avisos_en_campana(self.ticket, "Vencido"), [])
        self.assertEqual(avisar(self.ticket), 0)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.ans_alertado_en)
        self.assertFalse(AlertaOperativa.objects.filter(ticket=self.ticket).exists())
        self.assertFalse(Notificacion.objects.filter(clave__startswith=f"ans-{self.ticket.pk}").exists())

    @patch("apps.notificaciones.emails.correo_ans_por_vencer_usuario", return_value=True)
    def test_vencimiento_verificado_se_avisa_una_sola_vez(self, correo):
        self.assertIn(self.ticket, por_vencer(solo_verificados=True))
        self.assertEqual(avisar(self.ticket), 1)
        self.assertEqual(avisar(self.ticket), 0)
        correo.assert_called_once()
