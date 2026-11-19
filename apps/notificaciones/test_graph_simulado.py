"""Pruebas sin red ni credenciales reales del backend aportado localmente."""
import importlib
import sys
import types
from unittest.mock import Mock, patch

from django.core.mail import EmailMultiAlternatives, send_mail
from django.test import SimpleTestCase, override_settings


class GraphSimuladoTests(SimpleTestCase):
    def setUp(self):
        self.msal = types.ModuleType("msal")
        self.app = Mock()
        self.app.acquire_token_for_client.return_value = {"access_token": "token-falso"}
        self.msal.ConfidentialClientApplication = Mock(return_value=self.app)
        with patch.dict(sys.modules, {"msal": self.msal}):
            sys.modules.pop("config.graph_email_backend", None)
            self.modulo = importlib.import_module("config.graph_email_backend")
        self.env = patch.dict("os.environ", {"MS_GRAPH_CLIENT_ID": "id-ficticio", "MS_GRAPH_TENANT_ID": "tenant-ficticio", "MS_GRAPH_CLIENT_SECRET": "secreto-ficticio", "MS_GRAPH_SENDER": "sender@example.invalid"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def mensaje(self):
        mensaje = EmailMultiAlternatives("Prueba", "Texto", "sender@example.invalid", ["destino@example.invalid"])
        mensaje.attach_alternative("<p>Texto</p>", "text/html")
        return mensaje

    def test_autenticacion_peticion_y_aceptacion(self):
        with patch.object(self.modulo.requests, "post", return_value=Mock(status_code=202)) as post:
            self.assertEqual(self.modulo.GraphEmailBackend().send_messages([self.mensaje()]), 1)
        self.app.acquire_token_for_client.assert_called_once_with(scopes=["https://graph.microsoft.com/.default"])
        self.assertTrue(post.call_args.args[0].endswith("/sendMail"))
        self.assertEqual(post.call_args.kwargs["json"]["message"]["body"]["contentType"], "HTML")
        self.assertEqual(post.call_args.kwargs["json"]["message"]["toRecipients"][0]["emailAddress"]["address"], "destino@example.invalid")

    @override_settings(EMAIL_BACKEND="config.graph_email_backend.GraphEmailBackend", DEFAULT_FROM_EMAIL="sender@example.invalid")
    def test_django_utiliza_el_backend_configurado(self):
        with patch.dict(sys.modules, {"msal": self.msal, "config.graph_email_backend": self.modulo}), patch.object(self.modulo.requests, "post", return_value=Mock(status_code=202)) as post:
            self.assertEqual(send_mail("Asunto", "Texto", None, ["destino@example.invalid"]), 1)
        post.assert_called_once()

    def test_fallos_no_reintentan_automaticamente(self):
        for estado in (401, 403, 429, 500, 503):
            with self.subTest(estado=estado), patch.object(self.modulo.requests, "post", return_value=Mock(status_code=estado, headers={"Retry-After": "30"})) as post:
                with self.assertLogs("config.graph_email_backend", level="ERROR") as logs:
                    with self.assertRaisesRegex(RuntimeError, f"HTTP {estado}"):
                        self.modulo.GraphEmailBackend().send_messages([self.mensaje()])
                self.assertNotIn("token-falso", " ".join(logs.output))
                post.assert_called_once()

    def test_excepcion_externa_no_se_imprime_en_log_graph(self):
        with patch.object(self.modulo.requests, "post", side_effect=RuntimeError("token-privado-ficticio")):
            with self.assertLogs("config.graph_email_backend", level="ERROR") as logs:
                with self.assertRaises(RuntimeError):
                    self.modulo.GraphEmailBackend().send_messages([self.mensaje()])
        self.assertNotIn("token-privado-ficticio", " ".join(logs.output))
