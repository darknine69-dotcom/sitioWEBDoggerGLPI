from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.test import Client
from django.utils import timezone
from unittest.mock import patch
from datetime import timedelta

from apps.tickets.models import Ticket


class EncabezadoGlobalTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(email="cabecera-admin@example.com", nombre="Admin", password="x", rol="admin")
        self.tecnico = User.objects.create_user(email="cabecera-tecnico@example.com", nombre="Técnico", password="x", rol="tecnico")
        self.usuario = User.objects.create_user(email="cabecera-usuario@example.com", nombre="Usuario", password="x", rol="usuario")
        self.observador = User.objects.create_user(email="cabecera-observador@example.com", nombre="Observador", password="x", rol="observador")

    def test_perfil_comienza_con_su_nombre_para_cada_rol(self):
        for usuario, destino, nombre in ((self.admin, "tickets:dashboard", "Panel administrador"), (self.tecnico, "tickets:panel_tecnico", "Panel técnico"), (self.usuario, "tickets:mi_panel", "Mi panel"), (self.observador, "tickets:obs_monitoreo", "Monitoreo")):
            with self.subTest(rol=usuario.rol):
                self.client.force_login(usuario)
                response = self.client.get(reverse("accounts:ajustes"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<span aria-current="page" data-current-crumb>Mi perfil</span>')
                self.assertContains(response, 'href="#i-user"')
                self.assertEqual(response.content.count(b'data-profile-breadcrumb'), 1)
                self.assertContains(response, "Sesión iniciada")
                self.assertNotContains(response, "Última actividad:")

    def test_detalle_usa_codigo_real_y_enlace_autorizado(self):
        self.client.force_login(self.admin)
        ticket = Ticket.objects.create(titulo="Prueba", descripcion="Prueba", solicitante_nombre="Usuario", solicitante_email=self.usuario.email)
        response = self.client.get(reverse("tickets:detalle", args=[ticket.pk]))
        self.assertContains(response, f"Detalle {ticket.codigo}")
        self.assertContains(response, f'<a href="{reverse("tickets:lista")}">Tickets</a>')

    def test_programador_conserva_accion_y_encabezado(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("programador:panel_programador"))
        self.assertContains(response, "AGENDA Y PLANIFICACIÓN")
        self.assertContains(response, 'id="progCreateEvent"')
        self.assertContains(response, 'data-page-clock')

    def test_panel_principal_no_repite_la_ruta_actual(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("tickets:dashboard"))
        self.assertContains(response, '<span aria-current="page" data-current-crumb>Panel</span>')
        self.assertNotContains(response, 'Panel administrador</a>')

    def test_inicio_sesion_es_independiente_y_no_cambia_con_actividad(self):
        primero = timezone.now()
        segundo = primero + timedelta(seconds=10)
        otro_cliente = Client()
        with patch("apps.accounts.signals.timezone.now", return_value=primero):
            self.client.force_login(self.admin)
        with patch("apps.accounts.signals.timezone.now", return_value=segundo):
            otro_cliente.force_login(self.admin)
        response = self.client.get(reverse("tickets:dashboard"))
        self.assertEqual(response.context["encabezado"]["inicio_sesion"], primero)
        self.assertEqual(otro_cliente.get(reverse("tickets:dashboard")).context["encabezado"]["inicio_sesion"], segundo)
        self.admin.ultima_actividad = timezone.now()
        self.admin.save(update_fields=["ultima_actividad"])
        self.assertEqual(self.client.get(reverse("tickets:dashboard")).context["encabezado"]["inicio_sesion"], primero)

    def test_sesion_antigua_sin_fecha_no_inventa_inicio(self):
        self.client.force_login(self.admin)
        session = self.client.session
        del session["inicio_sesion"]
        session.save()
        response = self.client.get(reverse("tickets:dashboard"))
        self.assertIsNone(response.context["encabezado"]["inicio_sesion"])
