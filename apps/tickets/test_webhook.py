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
