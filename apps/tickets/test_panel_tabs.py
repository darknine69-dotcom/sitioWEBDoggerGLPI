"""Pestañas del Panel del técnico: Sin asignar, hover con color y lateral.

- Sin asignar vive como pestaña del panel (ya no en el menú lateral del
  técnico; el admin lo conserva).
- Cada indicador toma su color al pasar el mouse; sin chips month to date.
- La calificación del técnico va al pie del menú lateral.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Usuario
from apps.tickets.models import CalificacionTecnico, Ticket


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class PestanasPanelTest(TestCase):
    def setUp(self):
        self.tec = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )
        self.otro = Usuario.objects.create_user(
            email="tec2@x.com", password="x", nombre="Tec Dos",
            rol=Usuario.Rol.TECNICO,
        )
        self.client.force_login(self.tec)

    def _ticket(
        self,
        codigo,
        tecnico=None,
        estado=Ticket.Estado.ABIERTO,
        prioridad=Ticket.Prioridad.MEDIA,
    ):
        return Ticket.objects.create(
            codigo=codigo,
            titulo=f"T {codigo}",
            solicitante_nombre="Persona",
            solicitante_email="p@x.com",
            tecnico_asignado=tecnico,
            estado=estado,
            prioridad=prioridad,
        )

    def test_pestanas_sin_corporativo(self):
        html = self.client.get(reverse("tickets:panel_tecnico")).content.decode()
        for nombre in ("Panel", "Cola de solicitudes", "Mis solicitudes",
                       "Sin asignar"):
            self.assertIn(nombre, html)
        self.assertIn("dash-stat-row--tec dash-stat-row--mesas", html)
        self.assertNotIn("?vista=corp", html)
        # Sin pestaña "Corporativo" en el panel (el botón del chat flotante
        # sí dice Corporativo: es un <button>, no una pestaña <a>).
        self.assertNotIn(">Corporativo</a>", html)
        self.assertNotIn("dash-stat-mtd", html)

    def test_sin_asignar_muestra_solo_sin_tecnico(self):
        libre = self._ticket("HD-8001")
        self._ticket("HD-8002", tecnico=self.tec)
        self._ticket("HD-8003", tecnico=self.otro)
        self._ticket(
            "HD-8004", estado=Ticket.Estado.CERRADO,
        )
        respuesta = self.client.get(
            reverse("tickets:panel_tecnico"), {"vista": "sin"}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["sin_count"], 1)
        html = respuesta.content.decode()
        self.assertIn(libre.codigo, html)
        self.assertNotIn("HD-8002", html)
        self.assertNotIn("HD-8003", html)
        self.assertNotIn("HD-8004", html)
        self.assertIn(
            reverse("tickets:panel_tecnico_tomar", args=[libre.pk]), html
        )

    def test_sin_asignar_prioriza_fecha_reciente_sobre_prioridad(self):
        nuevo = self._ticket(
            "HD-8005", prioridad=Ticket.Prioridad.BAJA
        )
        antiguo_urgente = self._ticket(
            "HD-8006", prioridad=Ticket.Prioridad.URGENTE
        )
        Ticket.objects.filter(pk=antiguo_urgente.pk).update(
            fecha_creacion=timezone.now() - timedelta(days=2)
        )

        respuesta = self.client.get(
            reverse("tickets:panel_tecnico"),
            {"vista": "sin", "per_page_sol": 0},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.context["sin_page"].object_list[0].pk,
            nuevo.pk,
        )

    def test_hover_con_el_color_del_indicador(self):
        import re

        from django.contrib.staticfiles import finders

        html = self.client.get(reverse("tickets:panel_tecnico")).content.decode()
        clases = set(re.findall(r"dash-hov-[a-z]+", html))
        self.assertEqual(
            clases, {"dash-hov-total", "dash-hov-abiertos", "dash-hov-progreso", "dash-hov-resueltos"}
        )
        with open(finders.find("css/dogger-theme.css"), encoding="utf-8") as f:
            css = f.read()
        # Cada clase del HTML tiene su regla :hover en el CSS. El selector
        # no lleva el `a.` delante: los indicadores son enlaces, pero el
        # hover vale igual si alguna vista los pinta como caja.
        for clase in clases:
            self.assertIn(f".{clase}:hover", css)
        self.assertIn(".dash-stat-row--tec", css)
        self.assertIn(
            ".dash-stat:hover .dash-stat-icon .dash-stat-value { color: #fff; }",
            css,
        )

    def test_sin_asignar_sale_del_lateral(self):
        html_tec = self.client.get(
            reverse("tickets:panel_tecnico")
        ).content.decode()
        self.assertNotIn('sidebar-label">Sin asignar', html_tec)
        admin = get_user_model().objects.create_user(
            email="admin@x.com", password="x", nombre="Admin",
            rol=get_user_model().Rol.ADMIN,
        )
        self.client.force_login(admin)
        html_admin = self.client.get(
            reverse("tickets:dashboard")
        ).content.decode()
        self.assertNotIn('sidebar-label">Sin asignar', html_admin)
        # ... y Usuarios y roles ahora se llama Accesos.
        self.assertIn('sidebar-label">Accesos', html_admin)
        self.assertNotIn("Usuarios y roles</span>", html_admin)

    def test_calificacion_vive_en_el_lateral(self):
        votante = Usuario.objects.create_user(
            email="v@x.com", password="x", nombre="V",
            rol=Usuario.Rol.USUARIO,
        )
        CalificacionTecnico.objects.create(
            tecnico=self.tec, usuario=votante,
            valor=CalificacionTecnico.Valor.ME_GUSTA,
        )
        html = self.client.get(reverse("tickets:panel_tecnico")).content.decode()
        self.assertIn("sidebar-foot", html)
        self.assertIn("Tu calificación", html)
        self.assertNotIn("mi-gusta-card", html)
