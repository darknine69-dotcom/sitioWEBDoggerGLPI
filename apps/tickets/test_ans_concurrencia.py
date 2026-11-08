"""Pruebas de concurrencia optativas para bases de pruebas aisladas reales."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.tickets.models import Ticket
from apps.tickets.services.transiciones_ans import cambiar_estado_ans, EstadoTicketModificado


@skipUnless(os.getenv("DOGGER_ANS_CONCURRENCY_TESTS") == "1", "Requiere base de pruebas aislada y opt-in explícito")
class ConcurrenciaANSIntegrationTest(TransactionTestCase):
    def test_dos_cierres_con_estado_esperado(self):
        if connection.vendor not in ("postgresql", "microsoft", "mysql"):
            self.skipTest("La concurrencia debe validarse en un motor transaccional real")
        if connection.vendor == "mysql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s", [Ticket._meta.db_table])
                tabla = cursor.fetchone()
            self.assertIsNotNone(tabla, "No se encontró la tabla de tickets en la base aislada")
            self.assertEqual(tabla[0].upper(), "INNODB")
        ticket = Ticket.objects.create(titulo="Concurrencia", descripcion="Prueba", solicitante_nombre="Prueba")
        barrera = Barrier(2, timeout=10)

        def cerrar():
            close_old_connections()
            try:
                barrera.wait()
                try:
                    cambiar_estado_ans(ticket.pk, Ticket.Estado.CERRADO, estado_esperado=Ticket.Estado.ABIERTO)
                    return "cerrado"
                except EstadoTicketModificado:
                    return "conflicto"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(lambda _: cerrar(), range(2)))
        self.assertCountEqual(resultados, ["cerrado", "conflicto"])
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, Ticket.Estado.CERRADO)
        self.assertEqual(ticket.transiciones_ans.filter(tipo="cierre").count(), 1)
