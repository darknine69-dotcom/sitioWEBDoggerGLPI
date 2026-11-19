"""Concurrencia real: ejecutar solo contra una base SQL Server de pruebas aislada.

Requiere RUN_SQLSERVER_CONCURRENCY_TESTS=1 y la configuración de TEST de Django.
Nunca ejecuta estas pruebas con SQLite ni con la base de aplicación habitual.
"""
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase

from apps.tickets.models import Categoria, ConfiguracionAutoasignacion, DecisionAutoasignacion, PerfilAutoasignacion, Ticket
from apps.tickets.services.autoasignacion_transaccional import asignar_manual, asignar_ticket, coordinacion_asignacion
from apps.tickets.services.transiciones_ans import cambiar_estado_ans


@skipUnless(os.environ.get("RUN_SQLSERVER_CONCURRENCY_TESTS") == "1" and connection.vendor == "microsoft", "Requiere SQL Server de pruebas habilitado explícitamente")
class ConcurrenciaSqlServerTests(TransactionTestCase):
    def setUp(self):
        nombre = str(connection.settings_dict["NAME"]).lower()
        if not (nombre.startswith("test_") or nombre.endswith("_test")):
            self.fail("La conexión no apunta a una base de pruebas reconocible")
        self.categoria = Categoria.objects.create(grupo="Pruebas", nombre="Concurrencia")
        self.tecnicos = [get_user_model().objects.create_user(f"concurrente{i}@example.com", f"Técnico {i}", "clave", rol="tecnico") for i in range(2)]
        ConfiguracionAutoasignacion.objects.create(pk=1, activa=True)
        for tecnico in self.tecnicos:
            PerfilAutoasignacion.objects.create(tecnico=tecnico, habilitado=True, cobertura_general=True, capacidad=20)

    def ticket(self):
        return Ticket.objects.create(titulo="Prueba concurrente", categoria=self.categoria, prioridad="alta")

    def ejecutar_concurrente(self, funciones):
        barrera = threading.Barrier(len(funciones), timeout=15)
        def ejecutar(funcion):
            close_old_connections()
            try:
                barrera.wait()
                return funcion()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(funciones)) as ejecutor:
            resultados = [ejecutor.submit(ejecutar, funcion) for funcion in funciones]
            return [resultado.result(timeout=60) for resultado in resultados]

    def test_dos_creaciones_consideran_carga_confirmada(self):
        primero, segundo = self.ticket(), self.ticket()
        self.ejecutar_concurrente([lambda: asignar_ticket(primero.pk), lambda: asignar_ticket(segundo.pk)])
        primero.refresh_from_db()
        segundo.refresh_from_db()
        self.assertNotEqual(primero.tecnico_asignado_id, segundo.tecnico_asignado_id)
        self.assertEqual({primero.tecnico_asignado_id, segundo.tecnico_asignado_id}, {t.pk for t in self.tecnicos})

    def test_manual_confirmada_no_es_sobrescrita(self):
        ticket = self.ticket()
        self.ejecutar_concurrente([lambda: asignar_ticket(ticket.pk), lambda: asignar_manual(ticket.pk, self.tecnicos[0])])
        ticket.refresh_from_db()
        self.assertEqual(ticket.tecnico_asignado_id, self.tecnicos[0].pk)
        self.assertFalse(ticket.asignacion_automatica)

    def test_creacion_simultanea_desde_varios_puntos_con_carga_consistente(self):
        def crear_y_asignar(punto):
            ticket = Ticket.objects.create(titulo=f"Incidencia {punto}", categoria_id=self.categoria.pk,
                                           prioridad="alta", solicitante_punto=punto)
            asignar_ticket(ticket.pk)
            return ticket.pk

        puntos = [f"Sede {indice}" for indice in range(6)]
        ids = self.ejecutar_concurrente([lambda punto=punto: crear_y_asignar(punto) for punto in puntos])
        tickets = list(Ticket.objects.filter(pk__in=ids))
        self.assertEqual(len(tickets), 6)
        self.assertEqual({ticket.solicitante_punto for ticket in tickets}, set(puntos))
        for tecnico in self.tecnicos:
            self.assertEqual(sum(ticket.tecnico_asignado_id == tecnico.pk for ticket in tickets), 3)
        decisiones = DecisionAutoasignacion.objects.filter(ticket_id__in=ids)
        self.assertEqual(decisiones.count(), 6)
        self.assertEqual(sorted(decisiones.values_list("carga", flat=True)), [0, 0, 3, 3, 6, 6])
        self.assertEqual(ConfiguracionAutoasignacion.objects.get(pk=1).secuencia, 6)
        self.assertEqual(sorted(PerfilAutoasignacion.objects.values_list("orden_rotacion", flat=True)), [5, 6])

    def test_cierre_concurrente_con_asignacion(self):
        PerfilAutoasignacion.objects.filter(tecnico=self.tecnicos[1]).update(habilitado=False)
        previo = self.ticket()
        asignar_manual(previo.pk, self.tecnicos[0])
        nuevo = self.ticket()
        self.ejecutar_concurrente([lambda: cambiar_estado_ans(previo.pk, Ticket.Estado.CERRADO), lambda: asignar_ticket(nuevo.pk)])
        previo.refresh_from_db()
        nuevo.refresh_from_db()
        self.assertEqual(previo.estado, Ticket.Estado.CERRADO)
        self.assertIsNotNone(nuevo.tecnico_asignado_id)
        self.assertEqual(DecisionAutoasignacion.objects.filter(ticket=nuevo).count(), 1)
        self.assertIn(DecisionAutoasignacion.objects.get(ticket=nuevo).carga, (0, 3))

    def test_reapertura_concurrente_con_asignacion(self):
        PerfilAutoasignacion.objects.filter(tecnico=self.tecnicos[1]).update(habilitado=False)
        previo = self.ticket()
        asignar_manual(previo.pk, self.tecnicos[0])
        cambiar_estado_ans(previo.pk, Ticket.Estado.CERRADO)
        nuevo = self.ticket()
        self.ejecutar_concurrente([lambda: cambiar_estado_ans(previo.pk, Ticket.Estado.ABIERTO), lambda: asignar_ticket(nuevo.pk)])
        previo.refresh_from_db()
        self.assertEqual(previo.estado, Ticket.Estado.ABIERTO)
        self.assertEqual(DecisionAutoasignacion.objects.filter(ticket=nuevo).count(), 1)
        self.assertIn(DecisionAutoasignacion.objects.get(ticket=nuevo).carga, (0, 3))

    def test_saturacion_concurrente_no_supera_capacidad(self):
        PerfilAutoasignacion.objects.update(capacidad=3)
        tickets = [self.ticket() for _ in range(6)]
        self.ejecutar_concurrente([lambda ticket=ticket: asignar_ticket(ticket.pk) for ticket in tickets])
        self.assertEqual(Ticket.objects.filter(pk__in=[t.pk for t in tickets], tecnico_asignado__isnull=False).count(), 2)
        self.assertEqual(DecisionAutoasignacion.objects.filter(ticket__in=tickets, motivo="capacidad_insuficiente").count(), 4)

    def test_prioridad_concurrente_con_asignacion(self):
        PerfilAutoasignacion.objects.filter(tecnico=self.tecnicos[1]).update(habilitado=False)
        previo, nuevo = self.ticket(), self.ticket()
        asignar_manual(previo.pk, self.tecnicos[0])
        def cambiar_prioridad():
            with coordinacion_asignacion():
                ticket = Ticket.objects.select_for_update().get(pk=previo.pk)
                ticket.prioridad = "urgente"
                ticket.save(update_fields=["prioridad"])
        self.ejecutar_concurrente([cambiar_prioridad, lambda: asignar_ticket(nuevo.pk)])
        previo.refresh_from_db()
        self.assertEqual(previo.prioridad, "urgente")
        self.assertEqual(DecisionAutoasignacion.objects.filter(ticket=nuevo).count(), 1)
        self.assertIn(DecisionAutoasignacion.objects.get(ticket=nuevo).carga, (3, 5))

    def test_desasignacion_masiva_concurrente_con_reparto(self):
        from io import StringIO
        from django.core.management import call_command
        tecnico = self.tecnicos[0]
        PerfilAutoasignacion.objects.filter(tecnico=tecnico).update(habilitado=False)
        asignados = [self.ticket(), self.ticket()]
        for ticket in asignados:
            asignar_manual(ticket.pk, tecnico)
        nuevo = self.ticket()
        self.ejecutar_concurrente([
            lambda: call_command("eliminar_demo", email=tecnico.email, stdout=StringIO()),
            lambda: asignar_ticket(nuevo.pk),
        ])
        for ticket in asignados:
            ticket.refresh_from_db()
            self.assertIsNone(ticket.tecnico_asignado_id)
            self.assertTrue(ticket.asignacion_manual_protegida)
        nuevo.refresh_from_db()
        self.assertEqual(nuevo.tecnico_asignado_id, self.tecnicos[1].pk)
        self.assertEqual(DecisionAutoasignacion.objects.filter(ticket=nuevo).count(), 1)
