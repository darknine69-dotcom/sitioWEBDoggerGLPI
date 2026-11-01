"""Webhook GLPI: secret en tiempo constante y cerrado sin secret."""

import json

from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class WebhookSeguroTest(TestCase):
    def setUp(self):
        self.url = reverse("tickets:glpi_webhook")
        self.cuerpo = json.dumps({"action": "nada"})

    @override_settings(GLPI_WEBHOOK_SECRET="s3cr3t", DEBUG=False)
    def test_secret_malo_da_403(self):
        r = self.client.post(self.url, self.cuerpo,
                             content_type="application/json",
                             HTTP_X_DOGGER_SECRET="otro")
        self.assertEqual(r.status_code, 403)

    @override_settings(GLPI_WEBHOOK_SECRET="", DEBUG=False)
    def test_sin_secret_en_prod_rechaza(self):
        r = self.client.post(self.url, self.cuerpo,
                             content_type="application/json",
                             HTTP_X_DOGGER_SECRET="x")
        self.assertEqual(r.status_code, 403)

    @override_settings(GLPI_WEBHOOK_SECRET="s3cr3t", DEBUG=False)
    def test_secreto_unicode_invalido_no_produce_error_500(self):
        r = self.client.post(self.url, self.cuerpo, content_type="application/json", HTTP_X_DOGGER_SECRET="contraseña")
        self.assertEqual(r.status_code, 403)

    @override_settings(GLPI_WEBHOOK_SECRET="s3cr3t", DEBUG=False)
    def test_rechaza_json_que_no_es_objeto_y_cuerpo_grande(self):
        for cuerpo, esperado in (("[]", 400), ('{"x":"' + "a" * (256 * 1024) + '"}', 413)):
            with self.subTest(esperado=esperado):
                r = self.client.post(self.url, cuerpo, content_type="application/json", HTTP_X_DOGGER_SECRET="s3cr3t")
                self.assertEqual(r.status_code, esperado)

    @override_settings(GLPI_WEBHOOK_SECRET="s3cr3t", DEBUG=False)
    def test_rechaza_json_excesivamente_anidado(self):
        cuerpo = '{"x":' * 1100 + '0' + '}' * 1100
        r = self.client.post(self.url, cuerpo, content_type="application/json", HTTP_X_DOGGER_SECRET="s3cr3t")
        self.assertEqual(r.status_code, 400)

    @override_settings(GLPI_WEBHOOK_SECRET="s3cr3t", DEBUG=False)
    def test_secret_valido_acepta_objeto_json(self):
        r = self.client.post(self.url, self.cuerpo, content_type="application/json", HTTP_X_DOGGER_SECRET="s3cr3t")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
