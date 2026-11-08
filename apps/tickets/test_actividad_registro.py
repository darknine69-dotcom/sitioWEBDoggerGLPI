from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.tickets.models import Ticket, TicketComentario


class RegistroSeguimientosTest(TestCase):
    def setUp(self):
        usuarios = get_user_model()
        self.admin = usuarios.objects.create_user("admin-registro@example.com", "Admin", "clave", rol="admin", is_staff=True)
        self.tecnico = usuarios.objects.create_user("tecnico-registro@example.com", "Técnico", "clave", rol="tecnico")
        self.ticket = Ticket.objects.create(titulo="Caso", solicitante_nombre="Persona", solicitante_email="persona@example.com")
        TicketComentario.objects.create(ticket=self.ticket, usuario=self.tecnico, autor_nombre="Técnico", comentario="Información privada", es_interno=True)
        self.url = reverse("tickets:registro_seguimientos_api")

    def test_solo_administrador_consulta_y_no_expone_texto(self):
        self.client.force_login(self.tecnico)
        self.assertNotEqual(self.client.get(self.url).status_code, 200)
        self.client.force_login(self.admin)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos["total"], 1)
        self.assertEqual(datos["eventos"][0]["actor"], "Técnico")
        self.assertNotIn("Información privada", respuesta.content.decode())

    def test_filtro_por_rol_y_codigo(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url, {"rol": "usuario"}).json()["total"], 0)
        self.assertEqual(self.client.get(self.url, {"rol": "tecnico", "codigo": self.ticket.codigo}).json()["total"], 1)
