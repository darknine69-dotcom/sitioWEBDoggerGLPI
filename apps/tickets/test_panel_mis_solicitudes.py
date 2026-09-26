"""Reproduce el caso del usuario: 7 asignados, casi todos resueltos/antiguos."""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Usuario
from apps.tickets.models import Ticket


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class MisSolicitudesPanelTest(TestCase):
    def setUp(self):
        self.tecnico = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )
        self.client.force_login(self.tecnico)
        self.url = reverse("tickets:panel_tecnico")

    def _ticket(self, estado, dias, titulo="Ticket"):
        t = Ticket.objects.create(
            titulo=titulo,
            descripcion="d",
            prioridad=Ticket.Prioridad.MEDIA,
            estado=estado,
            solicitante_nombre="User",
        )
        t.tecnico_asignado = self.tecnico
        t.save()
        Ticket.objects.filter(pk=t.pk).update(
            fecha_creacion=timezone.now() - timedelta(days=dias)
        )
        t.refresh_from_db()
        return t

    def test_chip_resueltos_muestra_datos(self):
        r1 = self._ticket(Ticket.Estado.RESUELTO, 3, "Resuelto 1")
        r2 = self._ticket(Ticket.Estado.RESUELTO, 10, "Resuelto 2")
        self._ticket(Ticket.Estado.ABIERTO, 2, "Abierto 1")
        resp = self.client.get(self.url, {"vista": "mis", "estado": "resuelto", "rango": ""})
        self.assertContains(resp, "Resuelto 1")
        self.assertContains(resp, "Resuelto 2")
        self.assertNotContains(resp, "Abierto 1")
        # el contador de la pestana coincide con la lista
        ctx = resp.context
        self.assertEqual(ctx["mis_count"], 2)
        self.assertEqual(ctx["sv"], "todas")
        self.assertEqual(ctx["abiertas_count"], 2)
        self.assertEqual(ctx["sv_label"], "Resuelto")

    def test_pestana_no_miente_con_antiguos(self):
        self._ticket(Ticket.Estado.ABIERTO, 1, "Reciente")
        viejo = self._ticket(Ticket.Estado.ABIERTO, 90, "Viejo 90d")
        # por defecto: abiertas + 30 dias -> solo el reciente
        resp = self.client.get(self.url, {"vista": "mis"})
        self.assertEqual(resp.context["mis_count"], 1)
        self.assertEqual(resp.context["abiertas_count"], 1)
        self.assertNotContains(resp, "Viejo 90d")
        # al ampliar el rango aparece y el contador tambien
        resp = self.client.get(self.url, {"vista": "mis", "rango": ""})
        self.assertEqual(resp.context["mis_count"], 2)
        self.assertContains(resp, "Viejo 90d")
        # y la insignia de la pestana usa mis_count
        self.assertContains(resp, "Mis solicitudes <span>2</span>", html=False)

    def test_estado_vacio_ofrece_salida(self):
        self._ticket(Ticket.Estado.RESUELTO, 5, "Resuelto viejo")
        resp = self.client.get(self.url, {"vista": "mis", "sv": "abiertas"})
        self.assertEqual(resp.context["abiertas_count"], 0)
        self.assertContains(resp, "No hay solicitudes con estos filtros")
        self.assertContains(resp, "Ver todas mis solicitudes")

    def test_todas_muestra_resueltos(self):
        self._ticket(Ticket.Estado.RESUELTO, 5, "Resuelto R")
        self._ticket(Ticket.Estado.ABIERTO, 5, "Abierto A")
        resp = self.client.get(self.url, {"vista": "mis", "sv": "todas", "rango": ""})
        self.assertEqual(resp.context["mis_count"], 2)
        self.assertContains(resp, "Resuelto R")
        self.assertContains(resp, "Abierto A")
        # el select de vista refleja "todas" tambien para tecnicos
        self.assertContains(resp, '<option value="todas" selected>')
