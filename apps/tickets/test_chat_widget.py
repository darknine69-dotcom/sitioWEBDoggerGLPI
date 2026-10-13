"""Chat corporativo de soporte: hilos, permisos, adjuntos y widget."""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Usuario
from apps.notificaciones.models import Notificacion
from apps.tickets.models import (
    ElementoMiLista,
    ObservadorPunto,
    Punto,
    Ticket,
    TicketComentario,
)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ChatWidgetTest(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            email="ana@x.com", password="x", nombre="Ana", rol=Usuario.Rol.USUARIO
        )
        self.tec = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )
        self.admin = Usuario.objects.create_user(
            email="adm@x.com", password="x", nombre="Adm", rol=Usuario.Rol.ADMIN
        )
        self.obs = Usuario.objects.create_user(
            email="obs@x.com", password="x", nombre="Obs", rol=Usuario.Rol.OBSERVADOR
        )
        punto = Punto.objects.create(nombre="Zona Uno")
        ObservadorPunto.objects.create(observador=self.obs, punto=punto)
        self.ticket = Ticket.objects.create(
            titulo="T", descripcion="d", solicitante_nombre="Ana",
            solicitante_email="ana@x.com", solicitante_punto="Zona Uno",
            tecnico_asignado=self.tec,
        )
        self.ajeno = Ticket.objects.create(
            titulo="Otro", descripcion="d", solicitante_nombre="Otro",
            solicitante_email="otro@x.com", solicitante_punto="Zona Ajena",
        )

    def test_anonimo_no_entra(self):
        for nombre, args in (
            ("tickets:chat_tickets", []),
            ("tickets:chat_hilo", [self.ticket.pk]),
        ):
            respuesta = self.client.get(reverse(nombre, args=args) if args else reverse(nombre))
            self.assertEqual(respuesta.status_code, 302)

    def test_usuario_ve_solo_lo_suyo(self):
        self.client.force_login(self.usuario)
        datos = self.client.get(reverse("tickets:chat_tickets")).json()
        self.assertEqual([t["codigo"] for t in datos["tickets"]], [self.ticket.codigo])
        hilo = self.client.get(
            reverse("tickets:chat_hilo", args=[self.ticket.pk])).json()
        self.assertTrue(hilo["ok"])
        self.assertEqual(
            self.client.get(reverse("tickets:chat_hilo", args=[self.ajeno.pk])).status_code,
            403,
        )

    def test_responder_avisa_al_otro_lado(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse("tickets:chat_responder", args=[self.ticket.pk]),
            {"mensaje": "Sigo sin imprimir"},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["ok"])
        self.assertTrue(
            TicketComentario.objects.filter(
                ticket=self.ticket, comentario="Sigo sin imprimir").exists())
        self.assertTrue(Notificacion.objects.filter(usuario=self.tec).exists())

    def test_adjuntar_valida_tipo_y_tamano(self):
        self.client.force_login(self.usuario)
        url = reverse("tickets:chat_adjuntar", args=[self.ticket.pk])
        pdf = SimpleUploadedFile("doc.pdf", b"%PDF-1.4", content_type="application/pdf")
        respuesta = self.client.post(url, {"archivo": pdf})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["ok"])
        exe = SimpleUploadedFile("x.exe", b"bin", content_type="application/x-msdownload")
        self.assertEqual(self.client.post(url, {"archivo": exe}).status_code, 400)
        grande = SimpleUploadedFile("g.pdf", b"x" * (9 * 1024 * 1024),
                                    content_type="application/pdf")
        self.assertEqual(self.client.post(url, {"archivo": grande}).status_code, 400)

    def test_observador_solo_su_alcance(self):
        self.client.force_login(self.obs)
        datos = self.client.get(reverse("tickets:chat_tickets")).json()
        self.assertEqual([t["codigo"] for t in datos["tickets"]], [self.ticket.codigo])
        self.assertEqual(
            self.client.get(reverse("tickets:chat_hilo", args=[self.ajeno.pk])).status_code,
            403,
        )
        ElementoMiLista.objects.create(
            observador=self.obs, tipo=ElementoMiLista.TIPO_USUARIO,
            usuario_email="otro@x.com",
        )
        self.assertEqual(
            self.client.get(reverse("tickets:chat_hilo", args=[self.ajeno.pk])).status_code,
            200,
        )

    def test_tecnico_y_admin_gestionan(self):
        self.client.force_login(self.tec)
        self.assertEqual(
            self.client.get(reverse("tickets:chat_hilo", args=[self.ticket.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("tickets:chat_hilo", args=[self.ajeno.pk])).status_code,
            200,
        )
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("tickets:chat_hilo", args=[self.ticket.pk])).status_code,
            200,
        )

    def test_widget_en_base_para_autenticados(self):
        html = self.client.get(reverse("tickets:portal")).content.decode()
        self.assertNotIn("swFab", html)
        self.client.force_login(self.usuario)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn("swFab", html)
        self.assertIn("Estamos en línea", html)
        self.assertIn("/chat/api/hilo/", html)
