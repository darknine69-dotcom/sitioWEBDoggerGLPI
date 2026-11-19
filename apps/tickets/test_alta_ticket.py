"""
Alta de tickets desde el panel: el formulario nunca se dibuja el campo "modo",
asi que no puede llega en el POST. Antes de arreglarlo, el campo seguia siendo
obligatorio para el staff y toda alta devolvia "Este campo es obligatorio".
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.db import connection
from django.urls import reverse

from apps.tickets.management.commands.seed_categorias import CATEGORIAS
from apps.tickets.models import Categoria, ConfiguracionAutoasignacion, PerfilAutoasignacion, Ticket
from apps.tickets.sla import horas_por_prioridad
from apps.tickets.views import _auto_asignar_tecnico


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

    def test_usuario_final_no_puede_forzar_categoria(self):
        """La categoría visible es automática incluso si se manipula el POST."""
        self._entrar("usuario")
        categoria_manual = Categoria.objects.exclude(nombre__icontains="SIESA").first()
        self._alta(categoria=categoria_manual.pk)
        ticket = Ticket.objects.get()
        self.assertIn("SIESA", str(ticket.categoria))

    def test_alta_envia_a_glpi_y_notificaciones_el_tecnico_del_motor(self):
        from apps.tickets.services.glpi_client import _glpi_ids_asignados
        self._entrar("usuario")
        tecnico = get_user_model().objects.create_user(
            "asignado@dogger.com.co", "Asignado", "clave", rol="tecnico"
        )
        tecnico.glpi_user_id = 123
        tecnico.save(update_fields=["glpi_user_id"])
        ConfiguracionAutoasignacion.objects.create(pk=1, activa=True)
        PerfilAutoasignacion.objects.create(tecnico=tecnico, habilitado=True, cobertura_general=True, capacidad=20)
        with patch.object(connection.features, "has_select_for_update", True), \
             patch.object(connection.ops, "for_update_sql", return_value=""), \
             patch("apps.tickets.views.sync_ticket_to_glpi", return_value=None) as glpi, \
             patch("apps.tickets.views.notificar_ticket_creado") as notificar:
            respuesta = self.client.post(reverse("tickets:crear_ticket"), self._datos())
        self.assertEqual(respuesta.status_code, 302)
        ticket = Ticket.objects.get()
        self.assertEqual(ticket.tecnico_asignado_id, tecnico.pk)
        self.assertEqual(glpi.call_args.args[0].tecnico_asignado_id, tecnico.pk)
        self.assertEqual(_glpi_ids_asignados(glpi.call_args.args[0]), [123])
        self.assertEqual(notificar.call_args.args[0].tecnico_asignado_id, tecnico.pk)
        self.assertEqual(ticket.decisiones_autoasignacion.count(), 1)

    def test_alta_se_conserva_si_falla_autoasignacion(self):
        self._entrar("usuario")
        with patch("apps.tickets.services.autoasignacion_transaccional.asignar_ticket", side_effect=RuntimeError("fallo simulado")), \
             patch("apps.tickets.views.sync_ticket_to_glpi", return_value=None), \
             patch("apps.tickets.views.notificar_ticket_creado"):
            with self.assertLogs("apps.tickets.views", level="ERROR"):
                respuesta = self.client.post(reverse("tickets:crear_ticket"), self._datos())
        self.assertEqual(respuesta.status_code, 302)
        self.assertIsNone(Ticket.objects.get().tecnico_asignado_id)

    def test_fallo_glpi_no_revierte_asignacion_local(self):
        from apps.tickets.services.glpi_client import GlpiError
        self._entrar("usuario")
        tecnico = get_user_model().objects.create_user(
            "glpi@dogger.com.co", "Técnico", "clave", rol="tecnico"
        )
        ConfiguracionAutoasignacion.objects.create(pk=1, activa=True)
        PerfilAutoasignacion.objects.create(tecnico=tecnico, habilitado=True, cobertura_general=True, capacidad=20)
        with patch.object(connection.features, "has_select_for_update", True), \
             patch.object(connection.ops, "for_update_sql", return_value=""), \
             patch("apps.tickets.views.sync_ticket_to_glpi", side_effect=GlpiError("fallo simulado")), \
             patch("apps.tickets.views.notificar_ticket_creado") as notificar:
            respuesta = self.client.post(reverse("tickets:crear_ticket"), self._datos())
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Ticket.objects.get().tecnico_asignado_id, tecnico.pk)
        notificar.assert_called_once()

    def test_portal_y_panel_invocan_motor_con_ticket_persistido(self):
        for ruta, autenticado in (("tickets:portal", False), ("tickets:mi_panel", True)):
            with self.subTest(ruta=ruta):
                if autenticado:
                    self._entrar("usuario")
                with patch("apps.tickets.services.autoasignacion_transaccional.asignar_ticket", return_value=None) as motor, \
                     patch("apps.tickets.views.sync_ticket_to_glpi", return_value=None), \
                     patch("apps.tickets.views.notificar_ticket_creado"):
                    respuesta = self.client.post(reverse(ruta), self._datos())
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(Ticket.objects.filter(pk=motor.call_args.args[0]).exists())

    def test_incidente_urgente_va_al_tecnico_con_menor_carga(self):
        """La disponibilidad tiene prioridad en una caída de internet urgente."""
        tecnico_cargado = get_user_model().objects.create_user(
            "red-cargado@dogger.com.co", "Red cargado", "dogger1234", rol="tecnico"
        )
        tecnico_disponible = get_user_model().objects.create_user(
            "red-disponible@dogger.com.co", "Red disponible", "dogger1234", rol="tecnico"
        )
        categoria = Categoria.objects.get(grupo="Soporte TI", nombre="Red")
        categoria.tecnico_default = tecnico_cargado
        categoria.prioridad_default = Ticket.Prioridad.URGENTE
        categoria.save(update_fields=["tecnico_default", "prioridad_default"])
        Ticket.objects.create(
            titulo="Incidencia previa", categoria=categoria,
            prioridad=Ticket.Prioridad.URGENTE, estado=Ticket.Estado.ABIERTO,
            tecnico_asignado=tecnico_cargado,
        )
        ConfiguracionAutoasignacion.objects.create(pk=1, activa=True)
        for tecnico in (tecnico_cargado, tecnico_disponible):
            PerfilAutoasignacion.objects.create(tecnico=tecnico, habilitado=True, cobertura_general=True, capacidad=20)
        ticket = Ticket.objects.create(
            titulo="El internet no funciona", categoria=categoria,
            prioridad=Ticket.Prioridad.URGENTE, estado=Ticket.Estado.ABIERTO,
        )
        # Simula únicamente la sintaxis de bloqueo en SQLite, no concurrencia real.
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            self.assertTrue(_auto_asignar_tecnico(ticket))
        self.assertEqual(ticket.tecnico_asignado, tecnico_disponible)
        self.assertTrue(ticket.asignacion_automatica)
