import os
import subprocess
import sys

from django.test import SimpleTestCase
from cryptography.fernet import Fernet


class ProductionEmailSettingsTest(SimpleTestCase):
    def _settings(self, user, password, code="import config.settings", extra=None):
        env = os.environ.copy()
        env.update({"DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": "test-only-not-a-production-secret-1234567890", "SMOKE_TEST_SQLITE": "False", "DJANGO_EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend", "DJANGO_EMAIL_HOST_USER": user, "DJANGO_EMAIL_HOST_PASSWORD": password, "EMAIL_USER": "", "EMAIL_PASSWORD": ""})
        env.update({"DOGGER_FONDO_DURABLE": "True", "DOGGER_FERNET_KEY": Fernet.generate_key().decode()})
        env.update(extra or {})
        return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=20)

    def test_missing_smtp_credentials_fails_closed(self):
        result = self._settings("", "")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credenciales SMTP", result.stderr)

    def test_configured_smtp_does_not_use_console(self):
        result = self._settings("test@example.invalid", "test-only-password")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_sql_server_checks_certificate_by_default_in_production(self):
        result = self._settings("test@example.invalid", "test-only-password", "from config.settings import DATABASES; print(DATABASES['default']['OPTIONS']['extra_params'])", {"DATABASE_URL": "", "DB_EXTRA_PARAMS": ""})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "TrustServerCertificate=no")

    def test_smoke_database_does_not_inherit_database_url(self):
        result = self._settings("", "", "from config.settings import DATABASES; print(DATABASES['default']['ENGINE'])", {"SMOKE_TEST_SQLITE": "True", "DATABASE_URL": "postgres://test:test@invalid.example/test"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "django.db.backends.sqlite3")

    def test_smtp_has_a_finite_timeout(self):
        result = self._settings("test@example.invalid", "test-only-password", "from config.settings import EMAIL_TIMEOUT; print(EMAIL_TIMEOUT)", {"DJANGO_EMAIL_TIMEOUT": "15"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "15")

    def test_production_fallback_serves_only_public_avatars(self):
        code = "import django; django.setup(); from django.urls import resolve; print(resolve('/media/avatars/1/photo.png').func.__module__); print(resolve('/media/adjuntos/HD-1/a.pdf').func.__name__)"
        result = self._settings("", "", code, {"SMOKE_TEST_SQLITE": "True", "DJANGO_SETTINGS_MODULE": "config.settings", "DJANGO_SERVE_MEDIA": "True"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines(), ["django.views.static", "_adjunto_privado"])

    def test_durable_queue_requires_stable_valid_key_in_production(self):
        extra = {"DOGGER_FONDO_DURABLE": "True", "DOGGER_FERNET_KEY": ""}
        result = self._settings("test@example.invalid", "test-only-password", extra=extra)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DOGGER_FERNET_KEY", result.stderr)
        extra["DOGGER_FERNET_KEY"] = Fernet.generate_key().decode()
        result = self._settings("test@example.invalid", "test-only-password", extra=extra)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_queue_is_durable_by_default(self):
        code = "import os; os.environ.pop('DOGGER_FONDO_DURABLE', None); from config.settings import DOGGER_FONDO_DURABLE; print(DOGGER_FONDO_DURABLE)"
        result = self._settings("test@example.invalid", "test-only-password", code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "True")
