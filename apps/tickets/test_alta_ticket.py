"""
Alta de tickets desde el panel: el formulario nunca se dibuja el campo "modo",
asi que no puede llega en el POST. Antes de arreglarlo, el campo seguia siendo
obligatorio para el staff y toda alta devolvia "Este campo es obligatorio".
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.tickets.management.commands.seed_categorias import CATEGORIAS
from apps.tickets.models import Categoria, Ticket
from apps.tickets.sla import horas_por_prioridad


class AltaDeTicket(TestCase):
    @classmethod
    def setUpTestData(cls):
        for grupo, nombre, prioridad in CATEGORIAS:
            Categoria.objects.create(
                grupo=grupo,
                nombre=nombre,
                activo=True,
                prioridad_default=prioridad,
                ans_horas=horas_por_prioridad(prioridad),
            )

    def _entrar(self, rol):
        user = get_user_model().objects.create_user(
            "panel@dogger.com.co", "Panel", "dogger1234", rol=rol
        )
        self.client.login(username="panel@dogger.com.co", password="dogger1234")
        return user

    def _datos(self, **extra):
        datos = {
            "titulo": "no me funciona el sistema Siesa POS",
            "descripcion": "al intentar facturar sale un error de conexion",
            "prioridad": "media",
            "solicitante_nombre": "Prueba",
            "solicitante_email": "prueba@dogger.com.co",
            "solicitante_punto": "Local",
        }
        datos.update(extra)
        return datos

    def _alta(self, **extra):
        with patch("apps.tickets.views.sync_ticket_to_glpi", return_value=None):
            return self.client.post(reverse("tickets:crear_ticket"), self._datos(**extra))

    def test_staff_crea_sin_enviar_modo(self):
        """El panel no tiene campo "modo": el alta no puede fallar por eso."""
        self._entrar("tecnico")
        r = self._alta()
        self.assertEqual(r.status_code, 302, "el alta devolvio el formulario con errores")
        ticket = Ticket.objects.get()
        self.assertEqual(ticket.modo, Ticket.Modo.WEB)

    def test_staff_puede_forzar_el_modo(self):
        """Si el modo si viaja, se respeta."""
        self._entrar("tecnico")
        self._alta(modo=Ticket.Modo.TELEFONO)
        self.assertEqual(Ticket.objects.get().modo, Ticket.Modo.TELEFONO)

    def test_staff_sin_categoria_usa_la_sugerida(self):
        """Sin categoria en el POST, el servidor sugiere desde el titulo."""
        self._entrar("tecnico")
        self._alta()
        ticket = Ticket.objects.get()
        self.assertIsNotNone(ticket.categoria)
        self.assertIn("SIESA", str(ticket.categoria))

    def test_usuario_final_crea_sin_modo(self):
        self._entrar("usuario")
        self._alta()
        self.assertEqual(Ticket.objects.get().modo, Ticket.Modo.WEB)
