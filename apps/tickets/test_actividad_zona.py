from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Usuario
from apps.tickets.models import ElementoMiLista, MonitoreoAuditoria, Ticket, TicketComentario, ZonaObservador


class ActividadSupervisorTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(email="admin@actividad.test", nombre="Admin", password="x", rol="admin")
        self.supervisor = Usuario.objects.create_user(email="supervisor@actividad.test", nombre="Supervisor", password="x", rol="observador")
        self.otro = Usuario.objects.create_user(email="otro@actividad.test", nombre="Otro", password="x", rol="observador")
        zona = ZonaObservador.objects.create(observador=self.supervisor, nombre="Norte")
        ZonaObservador.objects.create(observador=self.otro, nombre="Norte")
        ElementoMiLista.objects.create(observador=self.supervisor, zona=zona, usuario_email="punto@actividad.test")
        ticket = Ticket.objects.create(titulo="Problema de red", descripcion="Sin conexión", solicitante_nombre="Punto", solicitante_email="punto@actividad.test")
        TicketComentario.objects.create(ticket=ticket, comentario="Respuesta técnica")
        MonitoreoAuditoria.objects.create(observador=self.supervisor, zona_nombre="Norte", accion="crear_zona", detalle="Registro propio")
        MonitoreoAuditoria.objects.create(observador=self.otro, zona_nombre="Norte", accion="crear_zona", detalle="Registro ajeno")
        self.url = reverse("tickets:monitoreo_actividad_supervisor", args=[self.supervisor.pk])

    def test_solo_incluye_la_actividad_del_supervisor(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        texto = str(respuesta.json())
        self.assertIn("Problema de red", texto)
        self.assertIn("Respuesta técnica", texto)
        self.assertIn("Registro propio", texto)
        self.assertNotIn("Registro ajeno", texto)

    def test_no_permite_acceso_a_observador(self):
        self.client.force_login(self.supervisor)
        self.assertNotEqual(self.client.get(self.url).status_code, 200)
