from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.tickets.models import Ticket


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class PanelAnsFilterTest(TestCase):
    def test_filters_use_real_ans_without_field_error_or_other_technician(self):
        user = get_user_model().objects.create_user("tec@example.com", "Tec", "clave", rol="tecnico")
        other = get_user_model().objects.create_user("otro@example.com", "Otro", "clave", rol="tecnico")
        for tecnico in (user, other):
            ticket = Ticket.objects.create(titulo="Caso", descripcion="Caso", solicitante_email="a@example.com", solicitante_nombre="A", tecnico_asignado=tecnico)
            from apps.tickets.tests_ans_fixtures import envejecer_ticket
            envejecer_ticket(ticket, timezone.now() - timedelta(days=30))
        self.client.force_login(user)
        vencidos = self.client.get(reverse("tickets:panel_tecnico"), {"vista": "mis", "sv": "vencidas"})
        self.assertEqual(vencidos.status_code, 200)
        self.assertEqual(vencidos.context["mis_count"], 1)
        hoy = self.client.get(reverse("tickets:panel_tecnico"), {"vista": "mis", "sv": "vencen-hoy"})
        self.assertEqual(hoy.status_code, 200)
        self.assertEqual(hoy.context["mis_count"], 0)
