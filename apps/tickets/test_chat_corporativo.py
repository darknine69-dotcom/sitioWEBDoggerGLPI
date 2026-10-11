"""Sala corporativa del chat: solo técnicos, admins y observadores.

El usuario final no la ve ni puede entrar: el selector de modo sale
únicamente en el encabezado del chat del staff.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Usuario
from apps.tickets.models import MensajeCorporativo


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class SalaCorporativaTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="admin@x.com", password="x", nombre="Admin", rol=Usuario.Rol.ADMIN
        )
        self.tecnico = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )
        self.obs = Usuario.objects.create_user(
            email="obs@x.com", password="x", nombre="Sup", rol=Usuario.Rol.OBSERVADOR
        )
        self.usuario = Usuario.objects.create_user(
            email="ana@x.com", password="x", nombre="Ana", rol=Usuario.Rol.USUARIO
        )
        self.hilo = reverse("tickets:chat_corporativo")
        self.enviar = reverse("tickets:chat_corporativo_enviar")

    def test_staff_lee_y_escribe(self):
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.get(self.hilo).json(), {"ok": True, "mensajes": []})
        r = self.client.post(self.enviar, {"mensaje": "Se cayó la sede norte"})
        self.assertEqual(r.status_code, 200)
        datos = r.json()
        self.assertTrue(datos["ok"])
        self.assertEqual(datos["mensaje"]["texto"], "Se cayó la sede norte")
        self.assertEqual(datos["mensaje"]["insignia"], "Técnico")
        self.assertTrue(datos["mensaje"]["propio"])
        # El admin lo ve; para él no es propio.
        self.client.force_login(self.admin)
        mensajes = self.client.get(self.hilo).json()["mensajes"]
        self.assertEqual(len(mensajes), 1)
        self.assertFalse(mensajes[0]["propio"])

    def test_observador_participa(self):
        self.client.force_login(self.obs)
        r = self.client.post(self.enviar, {"mensaje": "Presionen al técnico"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["mensaje"]["insignia"], "Observador")

    def test_usuario_final_no_entra(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(self.hilo).status_code, 403)
        self.assertEqual(
            self.client.post(self.enviar, {"mensaje": "hola"}).status_code, 403
        )

    def test_sin_sesion_redirige(self):
        self.assertEqual(self.client.get(self.hilo).status_code, 302)
        self.assertEqual(
            self.client.post(self.enviar, {"mensaje": "hola"}).status_code, 302
        )

    def test_valida_texto(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.enviar, {"mensaje": "  "}).status_code, 400)
        self.assertEqual(
            self.client.post(self.enviar, {"mensaje": "x" * 2001}).status_code, 400
        )

    def test_sin_permiso_de_chateo_no_escribe_pero_lee(self):
        self.tecnico.puede_responder_chat = False
        self.tecnico.save(update_fields=["puede_responder_chat"])
        self.client.force_login(self.tecnico)
        self.assertEqual(
            self.client.post(self.enviar, {"mensaje": "hola"}).status_code, 403
        )
        self.assertEqual(self.client.get(self.hilo).status_code, 200)

    def test_desde_trae_solo_lo_nuevo(self):
        self.client.force_login(self.admin)
        primero = self.client.post(self.enviar, {"mensaje": "uno"}).json()["mensaje"]
        self.client.post(self.enviar, {"mensaje": "dos"})
        mensajes = self.client.get(f"{self.hilo}?desde={primero['id']}").json()["mensajes"]
        self.assertEqual([m["texto"] for m in mensajes], ["dos"])
        self.assertEqual(MensajeCorporativo.objects.count(), 2)

    def test_selector_solo_para_staff(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("tickets:monitoreo_admin")).content.decode()
        self.assertIn("swModoCorp", html)
        self.assertIn("Corporativo", html)
        self.assertIn("Sala corporativa", html)
        self.assertIn('data-modo="soporte"', html)
        self.client.force_login(self.usuario)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertNotIn("swModoCorp", html)
