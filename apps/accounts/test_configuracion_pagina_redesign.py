from django.contrib.auth import get_user_model
from django.contrib.admin.models import LogEntry
from django.test import TestCase
from django.urls import reverse

from apps.tickets.models import ConfigSitio


class ConfiguracionPaginaRedesignTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(email="admin-test@example.com", password="x", nombre="Admin", rol=User.Rol.ADMIN)
        self.user = User.objects.create_user(email="user-test@example.com", password="x", nombre="Usuario", rol=User.Rol.USUARIO)
        self.url = reverse("accounts:configuracion_pagina")

    def test_guardado_ajax_y_validacion(self):
        self.client.force_login(self.admin)
        data = {"ajustes_pagina": "1", "whatsapp_numero": "3233742562", "correo_soporte": "test@example.com", "facebook_url": "https://facebook.com/dogger"}
        response = self.client.post(self.url, data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(ConfigSitio.cargar().whatsapp_numero, "3233742562")
        data["facebook_url"] = "javascript:alert(1)"
        response = self.client.post(self.url, data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ConfigSitio.cargar().facebook_url, "https://facebook.com/dogger")

    def test_usuario_no_puede_modificar_configuracion_o_permisos(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url, {"ajustes_pagina": "1"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("accounts:permisos"), {"uid": self.user.pk}).status_code, 404)

    def test_permiso_ajax(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("accounts:permisos"), {"uid": self.user.pk, f"perm_{self.user.pk}_cerrar": "1"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.puede_cerrar_tickets)

    def test_cambio_individual_guarda_auditoria_y_no_altera_otros_permisos(self):
        self.client.force_login(self.admin)
        self.user.puede_cerrar_tickets = False
        self.user.save(update_fields=["puede_cerrar_tickets"])
        antes = self.user.puede_crear_tickets
        response = self.client.post(reverse("accounts:permisos"), {"uid": self.user.pk, "permiso_unico": "cerrar", "valor": "1"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.puede_cerrar_tickets)
        self.assertEqual(self.user.puede_crear_tickets, antes)
        registro = LogEntry.objects.get(user_id=self.admin.pk, object_id=str(self.user.pk))
        self.assertIn("puede_cerrar_tickets", registro.change_message)
        self.assertIn("activado", registro.change_message)

    def test_permiso_individual_rechaza_campo_no_autorizado(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("accounts:permisos"), {"uid": self.user.pk, "permiso_unico": "is_superuser", "valor": "1"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_superuser)
