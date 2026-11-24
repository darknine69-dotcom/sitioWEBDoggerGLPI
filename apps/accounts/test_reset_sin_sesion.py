from datetime import timedelta
from django.core import signing
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import ResetPasswordToken, Usuario


class ResetSinSesionTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user("reset@test.com", "Prueba", "ClaveAnterior123", rol="usuario")
        self.token = ResetPasswordToken.generar(self.usuario)
        self.firma = signing.dumps(self.token.pk, salt="dogger-reset-enlace")
        self.enlace = reverse("accounts:enlace_reset_password", args=[self.firma])
        self.confirmar = reverse("accounts:restablecer_password")

    def test_flujo_sin_sesion_y_un_solo_uso(self):
        self.assertRedirects(self.client.get(self.enlace), self.confirmar)
        self.assertRedirects(self.client.post(self.confirmar, {"codigo": self.token.codigo}), self.confirmar)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("ClaveAnterior123"))
        self.assertContains(self.client.get(self.confirmar), "Guardar contraseña")
        respuesta = self.client.post(self.confirmar, {"password_nueva": "NuevaClave123", "password_confirmar": "NuevaClave123"})
        self.assertRedirects(respuesta, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("NuevaClave123"))
        self.token.refresh_from_db()
        self.assertTrue(self.token.usado)
        self.assertRedirects(self.client.get(self.enlace), reverse("accounts:reset_solicitar"))

    def test_enlace_no_sustituye_codigo(self):
        self.client.get(self.enlace)
        respuesta = self.client.post(self.confirmar, {"password_nueva": "NuevaClave123", "password_confirmar": "NuevaClave123"})
        self.assertEqual(respuesta.status_code, 200)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("ClaveAnterior123"))

    def test_codigo_caducado_no_cambia_clave(self):
        self.client.get(self.enlace)
        self.client.post(self.confirmar, {"codigo": self.token.codigo})
        ResetPasswordToken.objects.filter(pk=self.token.pk).update(creado=timezone.now() - timedelta(minutes=31))
        respuesta = self.client.post(self.confirmar, {"password_nueva": "NuevaClave123", "password_confirmar": "NuevaClave123"})
        self.assertRedirects(respuesta, reverse("accounts:reset_solicitar"))
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("ClaveAnterior123"))

    def test_enlace_falso_se_rechaza(self):
        self.assertRedirects(self.client.get(reverse("accounts:enlace_reset_password", args=["falso"])), reverse("accounts:reset_solicitar"))
