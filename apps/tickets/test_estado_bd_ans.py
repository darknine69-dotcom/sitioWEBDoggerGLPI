from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class DiagnosticoBaseANSTest(SimpleTestCase):
    @patch("apps.tickets.management.commands.estado_bd_ans.MigrationExecutor")
    @patch("apps.tickets.management.commands.estado_bd_ans.connection")
    def test_solo_muestra_metadatos_y_estado_de_migraciones(self, conexion, ejecutor):
        conexion.vendor = "postgresql"
        conexion.get_database_version.return_value = (16, 4)
        ejecutor.return_value.migration_plan.return_value = []
        ejecutor.return_value.loader.applied_migrations = {("tickets", "0047_ticket_ans_categoria_original_and_more")}
        salida = StringIO()
        call_command("estado_bd_ans", entorno="pruebas", stdout=salida)
        texto = salida.getvalue()
        self.assertIn("Motor: postgresql", texto)
        self.assertIn("Versión: 16.4", texto)
        self.assertIn("0047_ticket_ans_categoria_original_and_more: aplicada", texto)
        self.assertIn("0048_ticket_ans_version_ajuste_ticketajusteans: no aplicada", texto)

    @patch("apps.tickets.management.commands.estado_bd_ans.connection")
    def test_error_no_expone_detalles_de_conexion(self, conexion):
        conexion.vendor = "postgresql"
        conexion.ensure_connection.side_effect = RuntimeError("DATO_SENSIBLE")
        with self.assertRaises(CommandError) as error:
            call_command("estado_bd_ans", entorno="pruebas", stdout=StringIO())
        self.assertNotIn("DATO_SENSIBLE", str(error.exception))

    @patch("apps.tickets.management.commands.estado_bd_ans.connection")
    def test_no_crea_sqlite_inexistente(self, conexion):
        conexion.vendor = "sqlite"
        conexion.settings_dict = {"NAME": ""}
        with self.assertRaises(CommandError):
            call_command("estado_bd_ans", entorno="pruebas", stdout=StringIO())
        conexion.ensure_connection.assert_not_called()
