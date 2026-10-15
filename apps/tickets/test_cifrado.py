"""Tokens GLPI cifrados en reposo, legibles en la app."""

from django.db import connection
from django.test import TestCase, override_settings

from apps.tickets.cifrado import PREFIJO, cifrar, descifrar
from apps.tickets.models import ConfigSitio


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class CifradoTest(TestCase):
    def test_ida_y_vuelta(self):
        cfg = ConfigSitio.cargar()
        cfg.glpi_app_token = "secreto-abc-123"
        cfg.save()
        cfg.refresh_from_db()
        self.assertEqual(cfg.glpi_app_token, "secreto-abc-123")
        with connection.cursor() as cur:
            cur.execute('SELECT glpi_app_token FROM "ConfigSitio" WHERE id = 1')
            crudo = cur.fetchone()[0]
        self.assertTrue(crudo.startswith(PREFIJO))
        self.assertNotIn("secreto-abc-123", crudo)

    def test_legado_en_texto_plano_sigue_leyendo(self):
        cfg = ConfigSitio.cargar()
        with connection.cursor() as cur:
            cur.execute(
                'UPDATE "ConfigSitio" SET glpi_user_token = %s WHERE id = 1',
                ["legado-plano"],
            )
        cfg.refresh_from_db()
        self.assertEqual(cfg.glpi_user_token, "legado-plano")

    def test_vacio_no_se_cifra(self):
        self.assertEqual(cifrar(""), "")
        self.assertEqual(descifrar(""), "")
        self.assertEqual(descifrar("texto-plano"), "texto-plano")
