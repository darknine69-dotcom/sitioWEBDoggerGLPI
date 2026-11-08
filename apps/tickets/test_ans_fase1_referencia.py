"""Caracterización ANS actual sin base de datos ni migraciones.

Estas pruebas documentan comportamientos existentes, incluso inconsistencias;
no representan necesariamente la política deseada para la siguiente fase.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from types import SimpleNamespace

from django.db import models
from django.test import SimpleTestCase
from django.core.exceptions import PermissionDenied

from apps.tickets.models import Categoria, Ticket
from apps.tickets.sla import horas_por_prioridad
from apps.tickets.views import _agrupar_vencidos, _dashboard_metricas, _reportes_metricas_kpis
from apps.tickets.decorators import admin_required, staff_required, user_required
from apps.tickets.views_observador import _visible_a_observador


AHORA = datetime(2026, 11, 6, 15, tzinfo=dt_timezone.utc)


def ticket(horas=12, creado_hace=1, estado=Ticket.Estado.ABIERTO):
    categoria = Categoria(id=1, nombre="Prueba", ans_horas=horas)
    return Ticket(id=9000, codigo="HD-9000", titulo="Prueba", categoria=categoria,
                  prioridad="media", estado=estado,
                  fecha_creacion=AHORA - timedelta(hours=creado_hace))


def metricas_sin_consultas(tickets):
    with patch("apps.tickets.views.TicketComentario.objects.filter") as comentarios, \
            patch("apps.tickets.models.CalificacionTecnico.objects.filter") as votos:
        comentarios.return_value.values.return_value.annotate.return_value.values_list.return_value = []
        votos.return_value.count.return_value = 0
        votos.return_value.filter.return_value.count.return_value = 0
        return _dashboard_metricas(tickets)


class AnsReferenciaSinBaseTest(SimpleTestCase):
    def test_decoradores_por_rol(self):
        usuarios = {
            rol: SimpleNamespace(rol=rol, activo=True, is_authenticated=True,
                                 es_staff_helpdesk=rol in ("admin", "tecnico"))
            for rol in ("admin", "tecnico", "observador", "usuario")
        }
        for decorador, permitidos in ((admin_required, {"admin"}),
                                     (staff_required, {"admin", "tecnico"}),
                                     (user_required, {"usuario"})):
            vista = decorador(lambda request: "permitido")
            for rol, usuario in usuarios.items():
                with self.subTest(decorador=decorador.__name__, rol=rol):
                    request = SimpleNamespace(user=usuario)
                    if rol in permitidos:
                        self.assertEqual(vista(request), "permitido")
                    else:
                        with self.assertRaises(PermissionDenied):
                            vista(request)

    @patch("apps.tickets.views_observador.puntos_del_observador")
    def test_alcance_observador_sin_puntos_y_con_puntos(self, puntos):
        from unittest.mock import Mock
        consulta, usuario = Mock(), object()
        puntos.return_value = []
        _visible_a_observador(usuario, consulta)
        consulta.none.assert_called_once_with()
        puntos.return_value = ["Punto A"]
        _visible_a_observador(usuario, consulta)
        consulta.filter.assert_called_once_with(solicitante_punto__in=["Punto A"])

    def test_prioridades_y_categoria_toman_precedencia(self):
        self.assertEqual([horas_por_prioridad(p) for p in ("urgente", "alta", "media", "baja")], [2, 8, 12, 48])
        t = ticket(horas=8)
        t.prioridad = "urgente"
        self.assertEqual(t.ans_horas, 8)
        t.categoria = None
        self.assertEqual(t.ans_horas, 2)

    @patch("apps.tickets.models.timezone.now", return_value=AHORA)
    def test_ventana_urgente_y_limite_exacto(self, _now):
        t = ticket(horas=2, creado_hace=0)
        self.assertEqual(t.info_ans[0], "por-vencer")
        t.fecha_creacion = AHORA - timedelta(hours=2)
        self.assertEqual(t.info_ans[0], "vencido")

    def test_cambiar_prioridad_categoria_y_reasignacion(self):
        t = ticket(horas=8)
        original = t.fecha_limite_ans
        t.tecnico_asignado_id = 99
        self.assertEqual(t.fecha_limite_ans, original)
        t.prioridad = "urgente"
        self.assertEqual(t.fecha_limite_ans, original)
        t.categoria = Categoria(id=2, nombre="Otra", ans_horas=2)
        self.assertEqual(t.fecha_limite_ans, t.fecha_creacion + timedelta(hours=2))
        t.categoria = None
        t.prioridad = "baja"
        self.assertEqual(t.fecha_limite_ans, t.fecha_creacion + timedelta(hours=48))

    @patch.object(models.Model, "save", autospec=True)
    def test_reapertura_limpia_fechas_de_resolucion_y_cierre(self, _save):
        t = ticket()
        t.pk = None
        t._state.adding = False
        t._ans_transicion_autorizada = True
        t.fecha_resolucion = AHORA - timedelta(hours=2)
        t.fecha_cierre = AHORA - timedelta(hours=1)
        t.save()
        self.assertIsNone(t.fecha_resolucion)
        self.assertIsNone(t.fecha_cierre)

    @patch("django.utils.timezone.now", return_value=AHORA)
    def test_finalizado_tarde_y_divergencia_con_cierre(self, _now):
        t = ticket(horas=8, creado_hace=12, estado=Ticket.Estado.CERRADO)
        t.fecha_resolucion = t.fecha_creacion + timedelta(hours=7)
        t.fecha_cierre = t.fecha_creacion + timedelta(hours=10)
        self.assertEqual(t.info_ans[0], "resuelto")
        # El ticket de referencia no tiene instantánea histórica verificable.
        self.assertIsNone(metricas_sin_consultas([t])["sla_pct"])
        grupos = _agrupar_vencidos([t], lambda _: ("x", "X"))
        # Sin evidencia histórica tampoco se clasifica como infracción definitiva.
        self.assertEqual(grupos, [])
        t.fecha_resolucion = t.fecha_creacion + timedelta(hours=9)
        self.assertEqual(t.info_ans[0], "resuelto")
        self.assertIsNone(metricas_sin_consultas([t])["sla_pct"])

    @patch("django.utils.timezone.now", return_value=AHORA)
    def test_reportes_excluye_riesgo_y_finalizados_dashboard_los_cuenta(self, _now):
        riesgo = ticket(horas=8, creado_hace=7)
        finalizado = ticket(horas=8, creado_hace=10, estado=Ticket.Estado.RESUELTO)
        finalizado.fecha_resolucion = finalizado.fecha_creacion + timedelta(hours=3)
        panel = metricas_sin_consultas([riesgo, finalizado])
        reporte = _reportes_metricas_kpis([riesgo, finalizado])
        # Ambos ejemplos carecen de instantánea; no son cumplimiento definitivo.
        self.assertEqual((panel["sla_ok"], panel["sla_total"], panel["sla_sin"]), (0, 0, 2))
        self.assertEqual((reporte["sla_ok"], reporte["sla_no"]), (0, 0))

    @patch("django.utils.timezone.now", return_value=AHORA)
    def test_finalizado_sin_fecha_no_es_evaluable_en_dashboard(self, _now):
        t = ticket(estado=Ticket.Estado.RESUELTO)
        self.assertIsNone(metricas_sin_consultas([t])["sla_pct"])
