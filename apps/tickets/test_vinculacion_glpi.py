from unittest.mock import Mock, patch

from django.test import TestCase
from apps.accounts.models import Usuario
from apps.tickets.services.glpi_client import GlpiClient, GlpiError
from apps.tickets.services.vinculacion_glpi import vincular_cuenta_nueva


class VinculacionGlpiTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user("nuevo@test.com", "Nuevo", "clave", rol="usuario")

    @patch("apps.tickets.services.vinculacion_glpi.GlpiClient")
    def test_vincula_existente_sin_crear_duplicado(self, fabrica):
        cliente = fabrica.return_value
        cliente.available = True
        cliente.find_unique_user_by_email.return_value = 41
        self.assertTrue(vincular_cuenta_nueva(self.usuario))
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.glpi_user_id, 41)
        cliente.create_user.assert_not_called()
        cliente.kill_session.assert_called_once()

    @patch("apps.tickets.services.vinculacion_glpi.GlpiClient")
    def test_crea_cuando_no_existe(self, fabrica):
        cliente = fabrica.return_value
        cliente.available = True
        cliente.find_unique_user_by_email.return_value = None
        cliente.create_user.return_value = 42
        self.assertTrue(vincular_cuenta_nueva(self.usuario))
        self.assertEqual(self.usuario.glpi_user_id, 42)
        cliente.create_user.assert_called_once_with("Nuevo", "nuevo@test.com")

    @patch("apps.tickets.services.vinculacion_glpi.GlpiClient")
    def test_error_o_id_ocupado_no_se_asignan(self, fabrica):
        cliente = fabrica.return_value
        cliente.available = True
        cliente.find_unique_user_by_email.side_effect = GlpiError("incompleto")
        self.assertFalse(vincular_cuenta_nueva(self.usuario))
        cliente.create_user.assert_not_called()
        cliente.find_unique_user_by_email.side_effect = None
        cliente.find_unique_user_by_email.return_value = 41
        Usuario.objects.create_user("otro@test.com", "Otro", "clave", glpi_user_id=41)
        self.assertFalse(vincular_cuenta_nueva(self.usuario))
        self.usuario.refresh_from_db()
        self.assertIsNone(self.usuario.glpi_user_id)


class BuscarCorreoGlpiTests(TestCase):
    @patch("apps.tickets.services.glpi_client.requests.get")
    def test_solo_acepta_coincidencia_exacta_y_resultado_completo(self, get):
        cliente = GlpiClient.__new__(GlpiClient)
        cliente.base_url = "https://glpi.test"
        cliente.timeout = 1
        cliente._headers = Mock(return_value={})
        get.return_value.status_code = 200
        get.return_value.json.return_value = {"totalcount": 1, "data": [{"id": 7, "5": "Nuevo@Test.com"}]}
        self.assertEqual(cliente.find_unique_user_by_email("nuevo@test.com"), 7)
        get.return_value.json.return_value = {"totalcount": 1, "data": [{"id": 7, "5": "otro-nuevo@test.com"}]}
        with self.assertRaises(GlpiError):
            cliente.find_unique_user_by_email("nuevo@test.com")
        get.return_value.json.return_value = {"totalcount": 0, "data": []}
        self.assertIsNone(cliente.find_unique_user_by_email("nuevo@test.com"))
