from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Usuario


class UsuarioPanelPasswordTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="admin@x.com",
            nombre="Admin",
            password="AdminClave123",
            rol=Usuario.Rol.ADMIN,
        )
        self.usuario = Usuario.objects.create_user(
            email="ana@x.com",
            nombre="Ana",
            password="ClaveElegida123",
            rol=Usuario.Rol.USUARIO,
        )
        self.client.force_login(self.admin)

    def _guardar(self, password=""):
        return self.client.post(
            reverse("tickets:usuario_guardar"),
            {
                "pk": self.usuario.pk,
                "nombre": self.usuario.nombre,
                "email": self.usuario.email,
                "rol": self.usuario.rol,
                "activo": "on",
                "password1": password,
            },
        )

    def test_editar_con_clave_vacia_conserva_la_clave(self):
        respuesta = self._guardar()

        self.assertEqual(respuesta.status_code, 302)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("ClaveElegida123"))

    def test_clave_nueva_solo_cambia_cuando_se_escribe(self):
        respuesta = self._guardar("NuevaClave456")

        self.assertEqual(respuesta.status_code, 302)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("NuevaClave456"))

    def test_edicion_no_expone_clave_actual_y_permite_revelar_la_nueva(self):
        respuesta = self.client.get(reverse("tickets:usuarios"))
        html = respuesta.content.decode()

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn("ClaveElegida123", html)
        self.assertIn('data-password-toggle="u-pass"', html)
        self.assertIn("La contraseña guardada no se puede consultar.", html)
