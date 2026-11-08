from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.tickets.models import Ticket
from apps.tickets.views import _filtrar_estado, _punto_venta_panel_datos, _reportes_metricas_kpis, _reportes_metricas_usuarios


class ContadoresResolucionTest(TestCase):
    def test_resuelto_y_cierre_directo_se_cuentan_por_separado(self):
        usuario = get_user_model().objects.create_user("punto@example.com", "Punto", "clave", rol="usuario")
        comun = {"titulo": "Prueba", "descripcion": "Detalle", "solicitante_nombre": "Punto", "solicitante_email": usuario.email}
        resuelto = Ticket.objects.create(**comun, estado=Ticket.Estado.RESUELTO)
        from apps.tickets.services.transiciones_ans import cambiar_estado_ans
        resuelto = cambiar_estado_ans(resuelto.pk, Ticket.Estado.CERRADO)
        directo = Ticket.objects.create(**comun, estado=Ticket.Estado.CERRADO)
        self.assertTrue(resuelto.fue_resuelto)
        self.assertFalse(directo.fue_resuelto)
        datos = _punto_venta_panel_datos(usuario, {"zona_seguimiento_dashboard": {"zonas": []}})
        self.assertEqual(datos["estados"]["resueltos"], 1)
        self.assertEqual(datos["estados"]["cerrados"], 2)
        filtrados = _filtrar_estado(Ticket.objects.all(), Ticket.Estado.RESUELTO)
        self.assertEqual(list(filtrados.values_list("pk", flat=True)), [resuelto.pk])
        metricas = _reportes_metricas_kpis([resuelto, directo])
        self.assertEqual((metricas["total"], metricas["resueltos"], metricas["cerrados"]), (2, 1, 2))
        cuenta = _reportes_metricas_usuarios([resuelto, directo])[0]
        self.assertEqual((cuenta["resueltos"], cuenta["cerrados"]), (1, 2))
