from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.tickets.models import GlpiEvento, Ticket


class ActividadPuntoTest(TestCase):
    def test_vencimiento_se_muestra_solo_si_supero_el_limite(self):
        usuario = get_user_model().objects.create_user("punto@example.com", "Punto", "clave", rol="usuario")
        ticket = Ticket.objects.create(titulo="Vencido", descripcion="Detalle", solicitante_nombre="Punto", solicitante_email=usuario.email)
        from apps.tickets.tests_ans_fixtures import envejecer_ticket
        envejecer_ticket(ticket, timezone.now() - timedelta(days=30))
        otro = Ticket.objects.create(titulo="A tiempo", descripcion="Detalle", solicitante_nombre="Punto", solicitante_email=usuario.email)
        self.client.force_login(usuario)
        eventos = self.client.get(reverse("tickets:mi_panel"), {"actividad": "1"}).json()["eventos"]
        vencidos = [evento for evento in eventos if evento["texto"] == "Ticket vencido (ANS)"]
        self.assertEqual([evento["codigo"] for evento in vencidos], [ticket.codigo])
        self.assertNotEqual(ticket.codigo, otro.codigo)

    def test_actividad_propia_incluye_creacion_respuesta_y_papelera(self):
        usuario = get_user_model().objects.create_user("punto@example.com", "Punto", "clave", rol="usuario")
        otro = get_user_model().objects.create_user("otro@example.com", "Otro", "clave", rol="usuario")
        ticket = Ticket.objects.create(titulo="Solicitud", descripcion="Detalle", solicitante_nombre="Punto", solicitante_email=usuario.email)
        ajeno = Ticket.objects.create(titulo="Ajeno", descripcion="Detalle", solicitante_nombre="Otro", solicitante_email=otro.email)
        GlpiEvento.objects.create(ticket=ticket, tipo=GlpiEvento.Tipo.SEGUIMIENTO, descripcion="Respuesta del técnico")
        GlpiEvento.objects.create(ticket=ajeno, descripcion="Evento privado")
        ticket.mandar_a_la_papelera(usuario)
        self.client.force_login(usuario)
        response = self.client.get(reverse("tickets:mi_panel"), {"actividad": "1"})
        self.assertEqual(response.status_code, 200)
        eventos = response.json()["eventos"]
        textos = [evento["texto"] for evento in eventos]
        self.assertIn("Nueva solicitud creada", textos)
        self.assertIn("Respuesta del técnico", textos)
        self.assertIn("Solicitud enviada a la papelera", textos)
        self.assertNotIn("Evento privado", textos)
        self.assertTrue(all(not evento["ticket_url"] for evento in eventos))
