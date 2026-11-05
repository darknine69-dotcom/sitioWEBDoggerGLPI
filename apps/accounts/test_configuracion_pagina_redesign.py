from django.contrib.auth import get_user_model
from django.contrib.admin.models import LogEntry
from django.test import TestCase, override_settings
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

    def test_administrador_edita_horario_sin_modificar_contacto(self):
        self.client.force_login(self.admin)
        cfg = ConfigSitio.cargar()
        cfg.whatsapp_numero = "3233742562"
        cfg.save()
        respuesta = self.client.post(self.url, {"ajustes_horario": "1", "horario_dias": ["Lunes", "Domingo"], "horario_hora": ["08:00 - 17:00", "Cerrado"], "horario_nota": ["Soporte", ""]})
        self.assertEqual(respuesta.status_code, 302)
        cfg.refresh_from_db()
        self.assertEqual(cfg.whatsapp_numero, "3233742562")
        self.assertEqual(cfg.horario_detalle[1]["hora"], "Cerrado")
        from apps.tickets.context_processors import dogger_config
        from django.test import RequestFactory
        request = RequestFactory().get("/")
        request.user = self.admin
        self.assertEqual(dogger_config(request)["DOGGER"]["horario_detalle"], cfg.horario_detalle)

    def test_horario_incompleto_no_se_guarda(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {"ajustes_horario": "1", "horario_dias": ["Lunes"], "horario_hora": [""], "horario_nota": [""]})
        self.assertIsNone(ConfigSitio.cargar().horario_detalle)

    def test_limites_inactividad_solo_administrador_y_validacion(self):
        datos = {"ajustes_inactividad": "1", "inactividad_urgente": "1", "inactividad_alta": "4", "inactividad_media": "12", "inactividad_baja": "24"}
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url, datos).status_code, 404)
        self.client.force_login(self.admin)
        self.client.post(self.url, datos)
        self.assertEqual(ConfigSitio.cargar().limites_inactividad, {"urgente": 1, "alta": 4, "media": 12, "baja": 24})
        datos["inactividad_urgente"] = "0"
        self.client.post(self.url, datos)
        self.assertEqual(ConfigSitio.cargar().limites_inactividad["urgente"], 1)

    def test_escalamiento_requiere_administrador_plazo_y_destinatario(self):
        datos = {"ajustes_escalamiento": "1", "habilitado": "1", "horas": "2", "administradores": "1"}
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url, datos).status_code, 404)
        self.client.force_login(self.admin)
        self.client.post(self.url, {"ajustes_escalamiento": "1", "habilitado": "1", "horas": "2"})
        self.assertEqual(ConfigSitio.cargar().escalamiento_inactividad, {})
        self.client.post(self.url, datos)
        self.assertEqual(ConfigSitio.cargar().escalamiento_inactividad["horas"], 2)
        self.assertTrue(ConfigSitio.cargar().escalamiento_inactividad["habilitado"])

    def test_escalamiento_admite_tecnico_y_solicitante(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {"ajustes_escalamiento": "1", "habilitado": "1", "horas": "2", "tecnico": "1", "solicitante": "1"})
        regla = ConfigSitio.cargar().escalamiento_inactividad
        self.assertTrue(regla["habilitado"])
        self.assertTrue(regla["tecnico"])
        self.assertTrue(regla["solicitante"])
        self.assertFalse(regla["administradores"])
        self.assertFalse(regla["observadores"])

    def test_usuario_no_puede_editar_horario(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url, {"ajustes_horario": "1"}).status_code, 404)

    @override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
    def test_editor_solo_presenta_horarios_existentes(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("accounts:ajustes"))
        self.assertContains(respuesta, 'class="horario-fila"', count=3)
        self.assertContains(respuesta, "Agregar horario")

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
