"""Permisos por cuenta: el admin otorga cerrar/eliminar (usuarios) y reabrir."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.tickets.models import Ticket


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class PermisosRolesTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            email="adm@x.com", password="x", nombre="Adm", rol=User.Rol.ADMIN)
        self.usuario = User.objects.create_user(
            email="ana@x.com", password="x", nombre="Ana", rol=User.Rol.USUARIO)
        self.tec = User.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=User.Rol.TECNICO)

    def _ticket(self, estado=Ticket.Estado.ABIERTO):
        return Ticket.objects.create(
            titulo="T", descripcion="d", solicitante_nombre="Ana",
            solicitante_email="ana@x.com", estado=estado,
            tecnico_asignado=self.tec,
        )

    def test_pagina_solo_admin_y_guarda(self):
        self.client.force_login(self.usuario)
        self.assertEqual(
            self.client.get(reverse("accounts:permisos")).status_code, 404)
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("accounts:permisos"))
        self.assertRedirects(respuesta, reverse("accounts:ajustes") + "#pagina")
        respuesta = self.client.get(reverse("accounts:ajustes"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Permisos por cuenta")
        html = self.client.get(reverse("tickets:dashboard")).content.decode()
        self.assertNotIn('sidebar-label">Configuración', html)
        respuesta = self.client.post(reverse("accounts:permisos"), {
            f"perm_{self.usuario.pk}_cerrar": "1",
        })
        self.assertRedirects(respuesta, reverse("accounts:ajustes") + "#pagina")
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.puede_cerrar_tickets)
        self.assertFalse(self.usuario.puede_eliminar_tickets)

    def test_guarda_pagina_general(self):
        from apps.tickets.models import ConfigSitio

        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("accounts:configuracion_pagina"), {
            "ajustes_pagina": "1",
            "ajustes_actividad_glpi": "1",
            "correo_soporte": "nuevo@dogger.com.co",
            "siguiente": reverse("accounts:ajustes") + "#pagina",
        })
        self.assertRedirects(respuesta, reverse("accounts:ajustes") + "#pagina")
        self.assertEqual(ConfigSitio.cargar().correo_soporte, "nuevo@dogger.com.co")

    def test_cerrar_y_eliminar_exigen_permiso(self):
        ticket = self._ticket()
        self.client.force_login(self.usuario)
        self.usuario.puede_cerrar_tickets = False
        self.usuario.puede_eliminar_tickets = False
        self.usuario.save()
        self.assertEqual(
            self.client.post(reverse("tickets:mi_api_cerrar", args=[ticket.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse("tickets:mi_api_eliminar", args=[ticket.pk])).status_code,
            403,
        )

    def test_reabrir_exige_permiso_al_tecnico(self):
        ticket = self._ticket(estado=Ticket.Estado.CERRADO)
        self.client.force_login(self.tec)
        self.tec.puede_reabrir_tickets = False
        self.tec.save()
        respuesta = self.client.post(
            reverse("tickets:cambiar_estado", args=[ticket.pk]),
            {"estado": Ticket.Estado.ABIERTO, "next": "/panel/tickets/"},
            follow=True,
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, Ticket.Estado.CERRADO)
        self.assertContains(respuesta, "no te permite reabrir")

    def test_acciones_hasta_resuelto_y_cerrado(self):
        self._ticket(estado=Ticket.Estado.EN_PROGRESO)
        self.client.force_login(self.usuario)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn('data-action="eliminar"', html)
        self.assertIn('data-action="cerrar"', html)

    def test_saludo_predeterminado_en_chat(self):
        from django.contrib.staticfiles import finders

        with open(finders.find("js/chat-widget.js"), encoding="utf-8") as f:
            js = f.read()
        # Sin burbuja falsa: el saludo va en la caja del técnico y al
        # usuario le sale solo cuando el técnico le escribe de verdad.
        self.assertIn("¡Hola! Gracias por escribirnos", js)
        self.assertNotIn("Mesa de ayuda · Soporte", js)

    def test_crear_y_responder_exigen_permiso(self):
        from apps.tickets.models import Ticket

        ticket = Ticket.objects.create(
            titulo="T", descripcion="d", solicitante_nombre="Ana",
            solicitante_email="ana@x.com", tecnico_asignado=self.tec,
        )
        self.client.force_login(self.usuario)
        for campo in ("puede_crear_tickets", "puede_responder_chat"):
            setattr(self.usuario, campo, False)
        self.usuario.save()
        respuesta = self.client.get(reverse("tickets:crear_ticket"))
        self.assertRedirects(respuesta, reverse("tickets:mi_panel"))
        respuesta = self.client.post(
            reverse("tickets:chat_responder", args=[ticket.pk]),
            {"mensaje": "Hola"},
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_ficha_muestra_permisos_y_whatsapp_obedece(self):
        from apps.tickets.models import ConfigSitio, Ticket

        self.client.force_login(self.admin)
        html = self.client.get(
            reverse("tickets:usuario_ficha", args=[self.usuario.pk])
        ).content.decode()
        for etiqueta in ("Cerrar", "Eliminar", "Reabrir", "Crear", "Chatear"):
            self.assertIn(etiqueta, html)
        cfg = ConfigSitio.cargar()
        cfg.whatsapp_activo = False
        cfg.save()
        ticket = Ticket.objects.create(
            titulo="T", descripcion="d", solicitante_nombre="Ana",
            solicitante_email="ana@x.com",
        )
        self.client.force_login(self.usuario)
        html = self.client.get(
            reverse("tickets:mi_ticket", args=[ticket.pk])).content.decode()
        self.assertNotIn("btn-whatsapp", html)

    def test_atajos_por_defecto_segun_rol(self):
        self.client.force_login(self.usuario)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn("axFab", html)
        self.assertIn("Consultar ticket", html)

    def test_redes_en_footer_y_teams_en_contacto(self):
        from apps.tickets.models import ConfigSitio

        html = self.client.get(reverse("tickets:portal")).content.decode()
        self.assertIn("web.facebook.com/DoggerColombia", html)
        self.assertIn("instagram.com/dogger1996", html)
        self.assertNotIn("Teams de soporte", html)
        cfg = ConfigSitio.cargar()
        cfg.teams_activo = True
        cfg.teams_url = "https://teams.microsoft.com/l/chat/0/0"
        cfg.save()
        html = self.client.get(reverse("tickets:portal")).content.decode()
        self.assertIn("Teams de soporte", html)
        cfg.whatsapp_activo = False
        cfg.save()
        from apps.tickets.models import Ticket

        ticket = Ticket.objects.create(
            titulo="T", descripcion="d", solicitante_nombre="Ana",
            solicitante_email="ana@x.com",
        )
        self.client.force_login(self.usuario)
        html = self.client.get(
            reverse("tickets:mi_ticket", args=[ticket.pk])).content.decode()
        self.assertNotIn("btn-whatsapp", html)
