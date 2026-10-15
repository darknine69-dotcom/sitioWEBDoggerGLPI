"""Freno de fuerza bruta: login y código de reset se bloquean al insistir."""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ResetPasswordToken, Usuario
from apps.accounts.seguridad import bloqueado, limpiar, registrar_intento


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ThrottleTest(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(
            email="seg@x.com", password="Secreta123", nombre="Seg",
            rol=Usuario.Rol.USUARIO,
        )

    def test_helper_cuenta_y_bloquea(self):
        for _ in range(4):
            self.assertFalse(registrar_intento("t", "yo"))
        self.assertTrue(registrar_intento("t", "yo"))
        self.assertTrue(bloqueado("t", "yo"))
        limpiar("t", "yo")
        self.assertFalse(bloqueado("t", "yo"))

    def test_login_se_bloquea_a_los_6_fallos(self):
        url = reverse("accounts:login_usuario")
        datos = {"username": "seg@x.com", "password": "mala"}
        for _ in range(5):
            self.assertEqual(self.client.post(url, datos).status_code, 200)
        respuesta = self.client.post(url, datos)
        self.assertContains(respuesta, "Demasiados intentos")
        # Y con la clave buena también rebota mientras dure el bloqueo.
        buena = self.client.post(url, {"username": "seg@x.com", "password": "Secreta123"})
        self.assertContains(buena, "Demasiados intentos")

    def test_reset_se_bloquea_con_codigo_malo(self):
        token = ResetPasswordToken.generar(self.user)
        self.assertEqual(len(token.codigo), 6)
        sesion = self.client.session
        sesion["reset_pwd_email"] = self.user.email
        sesion.save()
        url = reverse("accounts:restablecer_password")
        for _ in range(5):
            self.assertEqual(
                self.client.post(url, {"codigo": "000000"}).status_code, 200)
        respuesta = self.client.post(url, {"codigo": "000000"}, follow=True)
        self.assertContains(respuesta, "Demasiados códigos")
