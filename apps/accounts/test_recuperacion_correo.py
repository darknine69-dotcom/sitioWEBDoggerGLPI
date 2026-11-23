from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ResetPasswordToken


class RecuperacionCorreoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user("ana@example.com", "Ana", "clave-segura", rol="usuario")
        self.url = reverse("accounts:reset_solicitar")

    def test_correo_no_registrado_no_envia_codigo(self):
        with patch("apps.accounts.views._enviar_codigo_reset") as enviar:
            respuesta = self.client.post(self.url, {"email": "otro@example.com"})
        self.assertEqual(respuesta.status_code, 302)
        enviar.assert_not_called()
        self.assertFalse(ResetPasswordToken.objects.exists())

    def test_cuenta_desactivada_no_recibe_codigo(self):
        self.usuario.is_active = False
        self.usuario.save(update_fields=["is_active"])
        with patch("apps.accounts.views._enviar_codigo_reset") as enviar:
            self.client.post(self.url, {"email": self.usuario.email})
        enviar.assert_not_called()
        self.assertFalse(ResetPasswordToken.objects.exists())

    def test_no_se_puede_modificar_el_correo_oculto_fijado(self):
        with patch("apps.accounts.views._enviar_codigo_reset") as enviar:
            respuesta = self.client.post(self.url + "?email=ana%40example.com", {"email": "otro@example.com"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "El correo cambió")
        enviar.assert_not_called()

    def test_correo_registrado_envia_a_la_cuenta_coincidente(self):
        with patch("apps.accounts.views._enviar_codigo_reset") as enviar:
            respuesta = self.client.post(self.url + "?manual=1", {"email": "ANA@example.com"})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(enviar.call_args.args[1].pk, self.usuario.pk)
        self.assertEqual(self.client.session["reset_pwd_email"], self.usuario.email)

    def test_correo_mal_formado_no_envia_codigo(self):
        with patch("apps.accounts.views._enviar_codigo_reset") as enviar:
            respuesta = self.client.post(self.url + "?manual=1", {"email": "ana@"})
        self.assertEqual(respuesta.status_code, 200)
        enviar.assert_not_called()

    def test_login_incluye_enlace_de_recuperacion(self):
        respuesta = self.client.get(reverse("accounts:login"))
        self.assertContains(respuesta, 'id="preparar-recuperacion"')

    def test_correo_preparado_queda_fijado_en_sesion_y_no_se_puede_alterar(self):
        otro = get_user_model().objects.create_user("otro@example.com", "Otro", "clave-segura", rol="usuario")
        preparar = self.client.post(self.url, {"accion": "preparar_correo", "email": self.usuario.email})
        self.assertEqual(preparar.status_code, 302)
        self.assertEqual(self.client.session["reset_pwd_destino_fijado"], self.usuario.email)
        pantalla = self.client.get(self.url)
        self.assertContains(pantalla, 'type="hidden" name="email" value="ana@example.com"')
        self.assertNotContains(pantalla, "Usar otro correo")
        with patch("apps.accounts.views._enviar_codigo_reset") as enviar:
            alterado = self.client.post(self.url + "?email=otro%40example.com", {"email": otro.email})
        self.assertEqual(alterado.status_code, 200)
        self.assertContains(alterado, "El correo cambió")
        self.assertContains(alterado, 'name="email" value="ana@example.com"')
        enviar.assert_not_called()

    def test_preparar_correo_no_envia_codigo_hasta_confirmar(self):
        with patch("apps.accounts.views._enviar_codigo_reset") as enviar:
            self.client.post(self.url, {"accion": "preparar_correo", "email": self.usuario.email})
            enviar.assert_not_called()
            self.client.post(self.url, {"email": self.usuario.email})
        enviar.assert_called_once()
        self.assertNotIn("reset_pwd_destino_fijado", self.client.session)

    def test_no_se_sustituye_destino_al_repetir_preparacion(self):
        self.client.post(self.url, {"accion": "preparar_correo", "email": self.usuario.email})
        respuesta = self.client.post(self.url, {"accion": "preparar_correo", "email": "otro@example.com"})
        self.assertContains(respuesta, "El correo ya está fijado")
        self.assertEqual(self.client.session["reset_pwd_destino_fijado"], self.usuario.email)

    def test_cancelar_limpia_el_destino_para_empezar_de_nuevo(self):
        self.client.post(self.url, {"accion": "preparar_correo", "email": self.usuario.email})
        respuesta = self.client.get(self.url + "?cancelar=1")
        self.assertRedirects(respuesta, reverse("accounts:login"))
        self.assertNotIn("reset_pwd_destino_fijado", self.client.session)
