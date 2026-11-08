from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import QuerySet
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.tickets.models import Categoria, Ticket, TicketAjusteANS, TicketTransicionANS
from apps.tickets.services.motor_ans import calcular_ans, evaluar_lote, historial_ans
from apps.tickets.views import _build_tecnico_dashboard, _dashboard_metricas, _dashboard_sparks, _reportes_metricas_kpis
from apps.tickets.views_observador import _contar_por_estado


class HistorialANSPersistidoTest(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(email="historial@example.invalid", nombre="Admin", password="x", rol="admin")
        self.ticket = Ticket.objects.create(titulo="Historial", descripcion="Prueba", solicitante_nombre="Prueba", prioridad="alta")
        self.inicio = self.ticket.ans_inicio_original
        self.original = self.ticket.ans_limite_original

    def evento(self, tipo, horas, ciclo):
        return TicketTransicionANS.objects.create(ticket=self.ticket, actor=self.actor, tipo=tipo, ciclo=ciclo,
            estado_anterior="abierto", estado_nuevo="resuelto", ocurrido_en=self.inicio + timedelta(hours=horas))

    def test_dos_ciclos_y_ajuste_posterior_no_cambia_primero(self):
        self.evento("resolucion", 7, 1)
        self.evento("cierre", 7.5, 1)
        self.evento("reapertura", 9, 2)
        TicketAjusteANS.objects.create(ticket=self.ticket, actor=self.actor, version=1, clave="historial-test",
            motivo="Prueba", limite_anterior=self.original, limite_nuevo=self.original + timedelta(hours=8),
            creado_en=self.inicio + timedelta(hours=10))
        Ticket.objects.filter(pk=self.ticket.pk)._reservar_version_ajuste(1)
        self.ticket.refresh_from_db()
        self.evento("resolucion", 12, 2)
        self.evento("cierre", 13, 2)
        with CaptureQueriesContext(connection) as consultas:
            resultados = historial_ans(self.ticket)
        self.assertEqual([r.estado for r in resultados], ["cumplido", "cumplido", "reapertura", "cumplido", "cumplido"])
        self.assertEqual(resultados[0].limite, self.original)
        self.assertEqual(resultados[-1].limite, self.original + timedelta(hours=8))
        self.assertLessEqual(len(consultas), 2)
        self.assertTrue(all(not q["sql"].lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE")) for q in consultas))

    def test_orden_ambiguo_y_version_incompleta(self):
        self.evento("resolucion", 7, 1)
        TicketAjusteANS.objects.create(ticket=self.ticket, actor=self.actor, version=1, clave="ambiguo-test",
            motivo="Prueba", limite_anterior=self.original, limite_nuevo=self.original + timedelta(hours=1),
            creado_en=self.inicio + timedelta(hours=7))
        Ticket.objects.filter(pk=self.ticket.pk)._reservar_version_ajuste(1)
        self.ticket.refresh_from_db()
        self.assertEqual(historial_ans(self.ticket)[0].calidad, "sin_informacion")
        Ticket.objects.filter(pk=self.ticket.pk)._reservar_version_ajuste(2)
        self.ticket.refresh_from_db()
        self.assertIsNone(historial_ans(self.ticket)[0].cumplimiento)

    def test_lotes_ajustados_consultan_numero_constante_y_no_guardan_cache(self):
        tickets = [self.ticket]
        for numero in range(8):
            tickets.append(Ticket.objects.create(titulo=f"Lote {numero}", descripcion="Prueba", solicitante_nombre="Prueba", prioridad="alta"))
        for indice, ticket in enumerate(tickets):
            TicketAjusteANS.objects.create(ticket=ticket, actor=self.actor, version=1, clave=f"lote-{indice}",
                motivo="Prueba", limite_anterior=ticket.ans_limite_original,
                limite_nuevo=ticket.ans_limite_original + timedelta(hours=2), creado_en=ticket.ans_inicio_original + timedelta(minutes=1))
            Ticket.objects.filter(pk=ticket.pk)._reservar_version_ajuste(1)
            ticket.refresh_from_db()
        for cantidad in (1, len(tickets)):
            with self.assertNumQueries(2):
                lote = evaluar_lote(tickets[:cantidad], ahora=self.inicio + timedelta(hours=3), incluir_historial=True)
            for ticket in tickets[:cantidad]:
                self.assertEqual(lote[ticket.pk][0], calcular_ans(ticket, ahora=self.inicio + timedelta(hours=3)))
        ticket = tickets[0]
        primero = evaluar_lote([ticket])[ticket.pk].limite
        TicketAjusteANS.objects.create(ticket=ticket, actor=self.actor, version=2, clave="lote-nuevo",
            motivo="Prueba", limite_anterior=primero, limite_nuevo=primero + timedelta(hours=1),
            creado_en=ticket.ans_inicio_original + timedelta(minutes=2))
        Ticket.objects.filter(pk=ticket.pk)._reservar_version_ajuste(2)
        self.assertEqual(ticket.ans_version_ajuste, 1)
        self.assertEqual(evaluar_lote([ticket])[ticket.pk].limite, primero + timedelta(hours=1))
        self.assertEqual(ticket.ans_version_ajuste, 1)

    def test_historicos_provisionales_cargan_categorias_por_lote(self):
        categoria = Categoria.objects.create(grupo="Prueba", nombre="Lote", ans_horas=8)
        tickets = [Ticket.objects.create(titulo=f"Legado {i}", descripcion="Prueba", solicitante_nombre="Prueba", categoria=categoria) for i in range(5)]
        for ticket in tickets:
            QuerySet.update(Ticket.objects.filter(pk=ticket.pk), ans_duracion_original=None,
                            ans_inicio_original=None, ans_limite_original=None, ans_verificacion="desconocido")
        tickets = list(Ticket.objects.filter(pk__in=[ticket.pk for ticket in tickets]))
        with self.assertNumQueries(2):
            resultados = evaluar_lote(tickets, permitir_provisional=True)
        self.assertTrue(all(resultado.provisional for resultado in resultados.values()))

    def test_reapertura_sin_terminal_no_produce_cumplimiento_verificado(self):
        self.evento("reapertura", 2, 2)
        self.evento("resolucion", 3, 2)
        self.assertTrue(all(r.calidad == "sin_informacion" for r in historial_ans(self.ticket)))

    def test_resolucion_duplicada_invalida_eventos_posteriores(self):
        self.evento("resolucion", 2, 1)
        self.evento("resolucion", 3, 1)
        self.evento("cierre", 4, 1)
        resultados = historial_ans(self.ticket)
        self.assertEqual(resultados[0].estado, "cumplido")
        self.assertTrue(all(r.calidad == "sin_informacion" for r in resultados[1:]))

    def test_evento_de_ciclo_incompleto_no_se_da_por_verificado(self):
        self.evento("resolucion", 2, 2)
        self.assertEqual(historial_ans(self.ticket)[0].calidad, "sin_informacion")

    def test_consultas_constantes_en_lotes_y_reporte(self):
        tickets = [self.ticket]
        for indice in range(199):
            tickets.append(Ticket.objects.create(titulo=f"Carga {indice}", descripcion="Prueba", solicitante_nombre="Prueba", prioridad="alta"))
        for cantidad in (1, 10, 50, 200):
            with self.subTest(cantidad=cantidad):
                with self.assertNumQueries(2):
                    evaluar_lote(tickets[:cantidad], incluir_historial=True)
                with self.assertNumQueries(1):
                    _reportes_metricas_kpis(tickets[:cantidad])
                with self.assertNumQueries(5):
                    _dashboard_metricas(tickets[:cantidad])
                with self.assertNumQueries(2):
                    _dashboard_sparks(tickets[:cantidad])

    def test_dashboard_tecnico_no_consulta_ajustes_por_ticket(self):
        tickets = [self.ticket]
        for numero in range(9):
            tickets.append(Ticket.objects.create(titulo=f"Panel {numero}", descripcion="Prueba", solicitante_nombre="Prueba", prioridad="alta"))
        for numero, ticket in enumerate(tickets):
            TicketAjusteANS.objects.create(ticket=ticket, actor=self.actor, version=1, clave=f"panel-{numero}",
                motivo="Prueba", limite_anterior=ticket.ans_limite_original,
                limite_nuevo=ticket.ans_limite_original + timedelta(hours=2), creado_en=ticket.ans_inicio_original + timedelta(minutes=1))
            Ticket.objects.filter(pk=ticket.pk)._reservar_version_ajuste(1)
        counts = []
        tabla_ajuste = TicketAjusteANS._meta.db_table.lower()
        tabla_transicion = TicketTransicionANS._meta.db_table.lower()
        for cantidad in (1, 10):
            consulta = Ticket.objects.filter(pk__in=[ticket.pk for ticket in tickets[:cantidad]])
            with CaptureQueriesContext(connection) as consultas:
                _build_tecnico_dashboard(consulta=consulta, incluir_pivot=False)
            counts.append(sum(tabla_ajuste in q["sql"].lower() or tabla_transicion in q["sql"].lower() for q in consultas))
        self.assertEqual(counts[0], counts[1], counts)
        conteos_observador = []
        for cantidad in (1, 10):
            consulta = Ticket.objects.filter(pk__in=[ticket.pk for ticket in tickets[:cantidad]])
            with CaptureQueriesContext(connection) as consultas:
                _contar_por_estado(consulta)
            conteos_observador.append(sum(tabla_ajuste in q["sql"].lower() or tabla_transicion in q["sql"].lower() for q in consultas))
        self.assertEqual(conteos_observador, [1, 1])
