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

    def test_pestana_muestra_todo_lo_asignado(self):
        self._ticket(Ticket.Estado.ABIERTO, 1, "Reciente")
        self._ticket(Ticket.Estado.ABIERTO, 90, "Viejo 90d")
        self._ticket(Ticket.Estado.RESUELTO, 200, "Resuelto 200d")
        self._ticket(Ticket.Estado.CERRADO, 400, "Cerrado 400d")
        # la pestana entra sin recortes: todo lo asignado, sin importar estado
        # ni antiguedad (si no, el tecnico veia una lista vacia)
        resp = self.client.get(self.url, {"vista": "mis"})
        ctx = resp.context
        self.assertEqual(ctx["sv"], "todas")
        self.assertEqual(ctx["rango"], "")
        self.assertEqual(ctx["mis_count"], 4)
        self.assertEqual(ctx["abiertas_count"], 4)
        for titulo in ("Reciente", "Viejo 90d", "Resuelto 200d", "Cerrado 400d"):
            self.assertContains(resp, titulo)
        # la insignia de la pestana cuenta lo mismo que "Total asignados"
        self.assertContains(resp, "Mis solicitudes <span>4</span>", html=False)

    def test_rango_30_dias_sigue_disponible(self):
        self._ticket(Ticket.Estado.ABIERTO, 1, "Reciente")
        self._ticket(Ticket.Estado.ABIERTO, 90, "Viejo 90d")
        resp = self.client.get(self.url, {"vista": "mis", "rango": "30"})
        self.assertEqual(resp.context["mis_count"], 1)
        self.assertContains(resp, "Reciente")
        self.assertNotContains(resp, "Viejo 90d")

    def test_solo_las_suyas(self):
        self._ticket(Ticket.Estado.ABIERTO, 1, "Mio")
        otro = Usuario.objects.create_user(
            email="otro@x.com", password="x", nombre="Otro", rol=Usuario.Rol.TECNICO
        )
        t = Ticket.objects.create(
            titulo="De otro",
            descripcion="d",
            prioridad=Ticket.Prioridad.MEDIA,
            estado=Ticket.Estado.ABIERTO,
            solicitante_nombre="User",
        )
        t.tecnico_asignado = otro
        t.save()
        resp = self.client.get(self.url, {"vista": "mis"})
        self.assertEqual(resp.context["mis_count"], 1)
        self.assertContains(resp, "Mio")
        self.assertNotContains(resp, "De otro")

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
