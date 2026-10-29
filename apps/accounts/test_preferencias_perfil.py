from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.notificaciones.models import Notificacion
from apps.notificaciones.services import crear


class PreferenciasPerfilTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            email="perfil@example.com", nombre="Perfil", password="clave12345", rol="usuario"
        )
        self.client.force_login(self.usuario)

    @patch("apps.accounts.views._glpi_available", return_value=False)
    def test_guardar_y_aplicar_preferencias_individuales(self, _glpi):
        respuesta = self.client.post(reverse("accounts:ajustes"), {
            "guardar_notificaciones": "1", "tickets_nuevos": "1", "eventos": "1",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.preferencias_notificaciones["recordatorios"])
        self.assertIsNone(crear(self.usuario, Notificacion.Tipo.TICKET_RECORDATORIO, "Plazo", "Aviso"))
        self.assertIsNotNone(crear(self.usuario, Notificacion.Tipo.TICKET_NUEVO, "Ticket", "Aviso"))

    @patch("apps.accounts.views._glpi_available", return_value=False)
    def test_perfil_solo_muestra_tickets_del_usuario(self, _glpi):
        respuesta = self.client.get(reverse("accounts:ajustes"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["perfil_ticket_total"], 0)
        self.assertNotIn("perfil_categoria_total", respuesta.context)

    @patch("apps.accounts.views._glpi_available", return_value=False)
    def test_ajustes_disponibles_y_opciones_por_rol(self, _glpi):
        for rol in ("usuario", "tecnico", "admin", "observador"):
            with self.subTest(rol=rol):
                cuenta = get_user_model().objects.create_user(
                    email=f"{rol}@example.com", nombre=rol, password="clave12345", rol=rol
                )
                self.client.force_login(cuenta)
                respuesta = self.client.get(reverse("accounts:ajustes"))
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, "Información personal")
                self.assertContains(respuesta, "Guardar preferencias")
                self.assertEqual("perfil_categoria_total" in respuesta.context, rol == "admin")
