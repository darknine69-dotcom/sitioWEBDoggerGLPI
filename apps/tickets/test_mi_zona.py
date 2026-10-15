"""Mi zona y presionar al técnico: el usuario ve quién lo gobierna."""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Usuario
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
class MiZonaSupervisorTest(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            email="ana@x.com", password="x", nombre="Ana", rol=Usuario.Rol.USUARIO
        )
        self.tec = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )
        self.sup = Usuario.objects.create_user(
            email="sup@x.com", password="x", nombre="Sup", rol=Usuario.Rol.OBSERVADOR
        )
        self.punto = Punto.objects.create(nombre="Zona Uno")
        ObservadorPunto.objects.create(observador=self.sup, punto=self.punto)
        ElementoMiLista.objects.create(
            observador=self.sup, tipo=ElementoMiLista.TIPO_USUARIO,
            usuario_email="ana@x.com",
        )
        self.ticket = Ticket.objects.create(
            titulo="Impresora", descripcion="d", solicitante_nombre="Ana",
            solicitante_email="ana@x.com", solicitante_punto="Zona Uno",
            tecnico_asignado=self.tec,
        )
        self.client.force_login(self.usuario)

    def test_mi_panel_muestra_zona_y_supervisor(self):
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn("Mi zona y supervisor", html)
        self.assertIn("Zona Uno", html)
        self.assertIn("Sup", html)
        self.assertIn("Presionar", html)
        self.assertIn(self.ticket.codigo, html)

    def test_presionar_crea_comentario_y_avisa(self):
        respuesta = self.client.post(
            reverse("tickets:mi_presionar", args=[self.ticket.pk]),
            {"mensaje": "Ayuda por favor"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(
            TicketComentario.objects.filter(
                ticket=self.ticket, comentario="Ayuda por favor",
                es_interno=False).exists())

    def test_presionar_ajeno_da_404(self):
        ajeno = Ticket.objects.create(
            titulo="Otro", descripcion="d", solicitante_nombre="Luis",
            solicitante_email="luis@x.com", tecnico_asignado=self.tec,
        )
        self.assertEqual(
            self.client.post(
                reverse("tickets:mi_presionar", args=[ajeno.pk]),
                {"mensaje": "Hola"}).status_code, 404)
        self.assertFalse(TicketComentario.objects.filter(ticket=ajeno).exists())

    def test_presionar_sin_mensaje_ni_tecnico_falla(self):
        self.assertEqual(
            self.client.post(
                reverse("tickets:mi_presionar", args=[self.ticket.pk]),
                {"mensaje": "  "}).status_code, 302)
        self.assertFalse(TicketComentario.objects.filter(ticket=self.ticket).exists())
        self.ticket.tecnico_asignado = None
        self.ticket.save()
        self.assertEqual(
            self.client.post(
                reverse("tickets:mi_presionar", args=[self.ticket.pk]),
                {"mensaje": "Hola"}).status_code, 302)
        self.assertFalse(TicketComentario.objects.filter(ticket=self.ticket).exists())

    def test_dashboard_de_zona_con_metricas(self):
        respuesta = self.client.get(reverse("tickets:mi_panel"))
        self.assertEqual(respuesta.status_code, 200)
        zd = respuesta.context["zona_dashboard"]
        self.assertEqual(len(zd["zonas"]), 1)
        zona = zd["zonas"][0]
        self.assertEqual(zona["nombre"], "Zona Uno")
        self.assertEqual(zona["total"], 1)
        self.assertEqual(zona["abiertos"], 1)
        self.assertEqual(zona["posicion"], 1)
        self.assertTrue(respuesta.context["zona_json"])
        html = respuesta.content.decode()
        self.assertIn("Rendimiento por zona", html)
        self.assertIn("Ranking de zonas", html)

    def test_presionar_zona_avisa_supervisores(self):
        from apps.notificaciones.models import Notificacion

        respuesta = self.client.post(
            reverse("tickets:mi_presionar_zona"),
            {"zona": "Zona Uno", "mensaje": "Ayuda en la zona"})
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Notificacion.objects.filter(
            usuario=self.sup, titulo__icontains="Zona Uno").exists())

    def test_presionar_zona_ajena_da_404(self):
        from apps.notificaciones.models import Notificacion

        respuesta = self.client.post(
            reverse("tickets:mi_presionar_zona"),
            {"zona": "Zona Ajena", "mensaje": "Hola"})
        self.assertEqual(respuesta.status_code, 404)
        self.assertFalse(Notificacion.objects.filter(
            titulo__icontains="Zona Ajena").exists())
