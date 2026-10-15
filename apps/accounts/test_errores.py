"""Páginas de error y sincronía de rol en sesión."""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Usuario


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class PaginasErrorTest(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            email="u@x.com", password="x", nombre="U", rol=Usuario.Rol.USUARIO
        )
        self.admin = Usuario.objects.create_user(
            email="a@x.com", password="x", nombre="A", rol=Usuario.Rol.ADMIN,
            is_staff=True,
        )

    def test_403_con_salida_a_su_pagina(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("tickets:usuarios"))
        self.assertEqual(respuesta.status_code, 403)
        html = respuesta.content.decode()
        self.assertIn("403", html)
        self.assertIn("Ir a mi página", html)

    def test_404_disenada(self):
        html = self.client.get("/esta-url-no-existe-xyz/").content.decode()
        self.assertIn("404", html)
        self.assertIn("error-page", html)

    def test_500_no_cuenta_detalles(self):
        from django.test import RequestFactory

        from apps.accounts.views import pagina_error

        respuesta = pagina_error(RequestFactory().get("/"))
        self.assertEqual(respuesta.status_code, 500)
        html = respuesta.content.decode()
        self.assertIn("500", html)
        self.assertNotIn("Traceback", html)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class RolSesionTest(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            email="u@x.com", password="x", nombre="U", rol=Usuario.Rol.USUARIO
        )

    def test_rol_cambiado_redirige_a_su_nueva_pagina(self):
        self.client.force_login(self.usuario)
        self.client.get(reverse("tickets:mi_panel"))  # fija rol_sesion=usuario
        self.usuario.rol = Usuario.Rol.TECNICO
        self.usuario.save()
        respuesta = self.client.get(reverse("tickets:mi_panel"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("tickets:panel_tecnico"), respuesta["Location"])
        sesion = self.client.session
        self.assertEqual(sesion["rol_sesion"], "tecnico")

    def test_sin_cambio_no_redirige(self):
        self.client.force_login(self.usuario)
        self.client.get(reverse("tickets:mi_panel"))
        respuesta = self.client.get(reverse("tickets:mi_panel"))
        self.assertEqual(respuesta.status_code, 200)
