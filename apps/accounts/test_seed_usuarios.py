import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import Usuario


class SeedUsuariosIdempotenteTest(TestCase):
    @override_settings(DEBUG=True)
    def test_ejecutar_seed_no_cambia_la_clave_de_una_cuenta_existente(self):
        usuario = Usuario.objects.create_superuser(
            email="admin@x.com",
            nombre="Admin",
            password="ClaveElegida123",
        )
        variables = {
            "SEED_ADMIN_EMAIL": "ADMIN@X.COM",
            "SEED_ADMIN_PASSWORD": "OtraClave456",
            "SEED_USUARIO_EMAIL": "prueba@x.com",
            "SEED_USUARIO_PASSWORD": "",
        }
        with patch.dict(os.environ, variables):
            call_command("seed_usuarios", stdout=StringIO(), stderr=StringIO())

        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password("ClaveElegida123"))
        self.assertFalse(usuario.check_password("OtraClave456"))
