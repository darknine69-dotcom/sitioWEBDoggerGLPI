"""Sala corporativa del chat: solo técnicos, admins y observadores.

El usuario final no la ve ni puede entrar: el selector de modo sale
únicamente en el encabezado del chat del staff.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Usuario
from apps.notificaciones.models import Notificacion
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

    def test_directo_entre_dos_no_lo_ve_un_tercero(self):
        self.client.force_login(self.tecnico)
        r = self.client.post(self.enviar, {"mensaje": "entre nos", "para": self.admin.pk})
        self.assertEqual(r.status_code, 200)
        # La sala sigue vacía: el directo no se mezcla.
        self.assertEqual(self.client.get(self.hilo).json(), {"ok": True, "mensajes": []})
        # El admin lo lee en su directo con el técnico.
        self.client.force_login(self.admin)
        hilo = self.client.get(f"{self.hilo}?para={self.tecnico.pk}").json()
        self.assertEqual([m["texto"] for m in hilo["mensajes"]], ["entre nos"])
        # El observador no lo ve ni en sala ni en su directo.
        self.client.force_login(self.obs)
        self.assertEqual(self.client.get(self.hilo).json(), {"ok": True, "mensajes": []})
        self.assertEqual(
            self.client.get(f"{self.hilo}?para={self.tecnico.pk}").json(),
            {"ok": True, "mensajes": []},
        )

    def test_directo_valida_colega(self):
        self.client.force_login(self.tecnico)
        # Uno mismo, un usuario final y un id raro no valen.
        for malo in (self.tecnico.pk, self.usuario.pk, 999999):
            r = self.client.post(self.enviar, {"mensaje": "x", "para": malo})
            self.assertEqual(r.status_code, 404)
            r = self.client.get(f"{self.hilo}?para={malo}")
            self.assertEqual(r.status_code, 404)

    def test_colegas_solo_staff_y_sin_uno_mismo(self):
        self.client.force_login(self.obs)
        datos = self.client.get(reverse("tickets:chat_colegas")).json()
        nombres = [c["nombre"] for c in datos["colegas"]]
        self.assertIn("Tec", nombres)
        self.assertIn("Admin", nombres)
        self.assertNotIn("Sup", nombres)
        self.assertNotIn("Ana", nombres)
        self.client.force_login(self.usuario)
        self.assertEqual(
            self.client.get(reverse("tickets:chat_colegas")).status_code, 403
        )

    def test_novedades_cuenta_sala_y_directos(self):
        novedades = reverse("tickets:chat_novedades")
        self.client.force_login(self.tecnico)
        self.assertEqual(
            self.client.get(novedades).json(),
            {"ok": True, "sala": {"ultimo": 0, "nuevos": 0}, "dms": {}, "total": 0},
        )
        # El admin escribe en sala y un directo al técnico.
        self.client.force_login(self.admin)
        self.client.post(self.enviar, {"mensaje": "a todos"})
        self.client.post(self.enviar, {"mensaje": "para ti", "para": self.tecnico.pk})
        # El técnico lo ve todo pendiente; lo propio no cuenta.
        self.client.force_login(self.tecnico)
        datos = self.client.get(novedades).json()
        self.assertEqual(datos["sala"]["nuevos"], 1)
        self.assertEqual(datos["dms"][str(self.admin.pk)]["nuevos"], 1)
        self.assertEqual(datos["total"], 2)
        # Visto la sala, solo queda el directo.
        datos = self.client.get(
            f"{novedades}?sala={datos['sala']['ultimo']}"
        ).json()
        self.assertEqual(datos["sala"]["nuevos"], 0)
        self.assertEqual(datos["total"], 1)
        # Visto el directo, queda en cero.
        ultimo_dm = datos["dms"][str(self.admin.pk)]["ultimo"]
        datos = self.client.get(
            f"{novedades}?sala={datos['sala']['ultimo']}&dm={self.admin.pk}:{ultimo_dm}"
        ).json()
        self.assertEqual(datos["total"], 0)

    def test_estado_diagnostica_para_staff(self):
        self.client.force_login(self.admin)
        datos = self.client.get(reverse("tickets:chat_estado")).json()
        self.assertTrue(datos["ok"])
        self.assertEqual(datos["tablas"]["ChatCorporativo"], 0)
        self.assertIn("0024_mensajecorporativo_destinatario", datos["migraciones_tickets"])
        self.client.force_login(self.usuario)
        self.assertEqual(
            self.client.get(reverse("tickets:chat_estado")).status_code, 403
        )

    def test_novedades_solo_staff(self):
        self.client.force_login(self.usuario)
        self.assertEqual(
            self.client.get(reverse("tickets:chat_novedades")).status_code, 403
        )

    def test_directo_avisa_en_la_campana_y_sala_no(self):
        self.client.force_login(self.tecnico)
        self.client.post(self.enviar, {"mensaje": "a todos"})
        self.assertFalse(
            Notificacion.objects.filter(tipo="sistema").exists()
        )
        self.client.post(self.enviar, {"mensaje": "oye", "para": self.admin.pk})
        avisos = Notificacion.objects.filter(usuario=self.admin, tipo="sistema")
        self.assertEqual(avisos.count(), 1)
        aviso = avisos.get()
        self.assertIn("Tec", aviso.titulo)
        self.assertIn("oye", aviso.mensaje)
        self.assertIn(f"#chat-corp-dm-{self.tecnico.pk}", aviso.url)

    def test_autor_siempre_identificable(self):
        self.tecnico.nombre = ""
        self.tecnico.save(update_fields=["nombre"])
        self.client.force_login(self.tecnico)
        datos = self.client.post(self.enviar, {"mensaje": "yo"}).json()
        self.assertEqual(datos["mensaje"]["autor"], "tec@x.com")

    def test_selector_solo_para_staff(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("tickets:monitoreo_admin")).content.decode()
        self.assertIn("swModoCorp", html)
        self.assertIn("Corporativo", html)
        self.assertIn("swColega", html)
        self.assertIn("Hablar con", html)
        self.assertIn('data-modo="soporte"', html)
        self.client.force_login(self.usuario)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertNotIn("swModoCorp", html)
        self.assertNotIn("swColega", html)
