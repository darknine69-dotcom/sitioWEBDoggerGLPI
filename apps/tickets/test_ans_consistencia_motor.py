from datetime import timedelta
from unittest.mock import patch

from django.db.models import QuerySet
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.tickets.models import Ticket, TicketTransicionANS
from apps.tickets.services.motor_ans import calcular_ans
from apps.tickets.services.transiciones_ans import cambiar_estado_ans
from apps.tickets.views import _dashboard_metricas, _dashboard_sparks, _reportes_metricas_kpis, _eventos_panel_punto
from apps.tickets.ans_avisos import por_vencer
from apps.tickets.views_observador import _estado_de, ESTADO_ROJO


class ConsistenciaIndicadoresANSTest(TestCase):
    def setUp(self):
        self.ticket = Ticket.objects.create(titulo="Consistencia", descripcion="Prueba", solicitante_nombre="Prueba", prioridad="alta")

    def test_limite_exacto_coincide_en_motor_dashboard_y_observador(self):
        usuario = get_user_model().objects.create_user("punto-consistencia@example.invalid", "Punto", "x", rol="usuario")
        self.ticket.solicitante_email = usuario.email
        self.ticket.save(update_fields=["solicitante_email"])
        instante = self.ticket.ans_limite_original
        with patch("django.utils.timezone.now", return_value=instante):
            resultado = calcular_ans(self.ticket, ahora=instante)
            metricas = _dashboard_metricas([self.ticket])
            series = _dashboard_sparks([self.ticket])
            color = _estado_de(self.ticket, instante)
            estado_compatible = self.ticket.info_ans[0]
            reporte = _reportes_metricas_kpis([self.ticket])
            alertas = por_vencer(consulta=Ticket.objects.filter(pk=self.ticket.pk), solo_sin_avisar=False)
            eventos = _eventos_panel_punto(usuario)
        self.assertEqual(resultado.estado, "vencido")
        self.assertEqual(estado_compatible, "vencido")
        self.assertEqual(metricas["vencidos"], 1)
        self.assertEqual(metricas["vencidos_pendientes"], 1)
        self.assertEqual(sum(series["vencidos"]), 1)
        self.assertEqual(color, ESTADO_ROJO)
        self.assertEqual(reporte["vencidos"], 1)
        self.assertEqual(alertas[0].ans_estado, "vencido")
        self.assertTrue(any(fila["texto"] == "Ticket vencido (ANS)" for fila in eventos))

    def test_historico_desconocido_no_entra_en_cumplimiento_definitivo(self):
        QuerySet.update(Ticket.objects.filter(pk=self.ticket.pk), ans_verificacion="desconocido", ans_limite_original=None)
        self.ticket.refresh_from_db()
        metricas = _dashboard_metricas([self.ticket])
        self.assertEqual(metricas["sla_total"], 0)
        self.assertEqual(metricas["sla_sin"], 1)
        self.assertIsNone(metricas["sla_pct"])

    def test_historial_contradictorio_no_cuenta_en_dashboard_ni_reportes(self):
        ticket = cambiar_estado_ans(self.ticket.pk, Ticket.Estado.RESUELTO)
        primero = ticket.transiciones_ans.get(tipo="resolucion")
        TicketTransicionANS.objects.create(ticket=ticket, tipo="resolucion", ciclo=1,
            estado_anterior="abierto", estado_nuevo="resuelto", ocurrido_en=primero.ocurrido_en + timedelta(seconds=1))
        self.assertEqual(calcular_ans(ticket).estado, "sin_informacion")
        dashboard = _dashboard_metricas([ticket])
        reporte = _reportes_metricas_kpis([ticket])
        self.assertEqual((dashboard["sla_total"], dashboard["sla_sin"]), (0, 1))
        self.assertEqual((reporte["sla_ok"], reporte["sla_no"]), (0, 0))
