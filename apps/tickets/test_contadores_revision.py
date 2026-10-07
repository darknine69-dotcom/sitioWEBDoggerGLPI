"""Contadores que aparecen con el evento y se limpian al revisar.

Comprueba lo que se pidió de los avisos:

- El morrito del menú sube cuando pasa algo y baja en cuanto se entra a la
  pantalla que toca (nada de números congelados).
- El texto del aviso se redacta según el rol: al administrador se le dice
  "Se han registrado 3 tickets", no "Tienes 3 tickets".
- La ventana emergente sale centrada y con los botones "Ver" y "OK".
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.notificaciones import services as avisos
from apps.notificaciones.models import Notificacion
from apps.tickets.models import Ticket


def _crear_ticket(codigo, prioridad="normal", asignado=None, solicitante="persona@dogger.com.co"):
    return Ticket.objects.create(
        codigo=codigo,
        titulo=f"Prueba {codigo}",
        solicitante_nombre="Persona",
        solicitante_email=solicitante,
        prioridad=prioridad,
        tecnico_asignado=asignado,
    )


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ContadoresPorRevisionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.usuario = User.objects.create_user(
            "persona@dogger.com.co", "Persona", "x", rol="usuario"
        )
        cls.tecnico = User.objects.create_user(
            "tec@dogger.com.co", "Tecnico", "x", rol="tecnico"
        )
        cls.admin = User.objects.create_user(
            "jefe@dogger.com.co", "Jefe", "x", rol="admin"
        )

    def _no_leidas(self, usuario):
        self.client.force_login(usuario)
        return self.client.get(reverse("notificaciones:api")).json()["no_leidas"]

    # ---------------- el contador aparece y desaparece ----------------
    def test_el_contador_del_usuario_sube_y_baja_al_revisar(self):
        ticket = _crear_ticket("HD-5001")
        base = self._no_leidas(self.usuario)

        avisos.ticket_cerrado(ticket)
        self.assertEqual(self._no_leidas(self.usuario), base + 1)

        # Entrar a Mi panel es revisarlo: el contador queda en cero.
        self.client.get(reverse("tickets:mi_panel"))
        self.assertEqual(self._no_leidas(self.usuario), 0)

    def test_entrar_al_dashboard_limpia_el_contador_del_admin(self):
        ticket = _crear_ticket("HD-5002", asignado=self.tecnico)
        avisos.ticket_creado(ticket)
        self.assertGreater(self._no_leidas(self.admin), 0)

        self.client.get(reverse("tickets:dashboard"))
        self.assertEqual(self._no_leidas(self.admin), 0)

    def test_al_usuario_no_le_cuenta_el_aviso_de_su_propia_solicitud(self):
        """Crear un ticket no es "algo por revisar" para quien lo pidió."""
        _crear_ticket("HD-5003")
        self.client.force_login(self.usuario)
        self.client.get(reverse("tickets:mi_panel"))
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertNotIn("por revisar</span>", html)

    def test_tras_cancelar_una_solicitud_el_usuario_no_queda_con_avisos(self):
        ticket = _crear_ticket("HD-5004", asignado=self.tecnico)
        self.client.force_login(self.usuario)
        self.client.post(reverse("tickets:mi_api_eliminar", args=[ticket.pk]))
        self.client.get(reverse("tickets:mi_papelera"))
        self.assertEqual(self._no_leidas(self.usuario), 0)

    # ---------------- el texto según el rol ----------------
    def test_al_admin_se_le_dice_que_se_registraron_tickets(self):
        _crear_ticket("HD-5010")
        avisos.recordatorios(self.admin)
        aviso = Notificacion.objects.get(
            usuario=self.admin, clave__startswith="rec:registrados:"
        )
        self.assertEqual(aviso.titulo, "Se han registrado 1 ticket activo")

        _crear_ticket("HD-5011")
        _crear_ticket("HD-5012")
        avisos.recordatorios(self.admin)
        aviso.refresh_from_db()
        self.assertEqual(aviso.titulo, "Se han registrado 3 tickets activos")

    def test_el_admin_no_recibe_el_recordatorio_de_sus_tickets_asignados(self):
        _crear_ticket("HD-5013", asignado=self.tecnico)
        avisos.recordatorios(self.admin)
        self.assertFalse(
            Notificacion.objects.filter(
                usuario=self.admin, clave__startswith="rec:asignados:"
            ).exists()
        )

    def test_al_tecnico_si_se_le_dice_tienes_tus_tickets(self):
        _crear_ticket("HD-5014", asignado=self.tecnico)
        avisos.recordatorios(self.tecnico)
        aviso = Notificacion.objects.get(
            usuario=self.tecnico, clave__startswith="rec:asignados:"
        )
        self.assertEqual(aviso.titulo, "Tienes 1 ticket activo")

    # ---------------- la ventana emergente ----------------
    def test_la_emergente_tiene_botones_ver_y_ok(self):
        ticket = _crear_ticket("HD-5020")
        avisos.ticket_cerrado(ticket)
        self.client.force_login(self.usuario)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn("notifPopup", html)
        self.assertIn("notif-popup-ver", html)
        self.assertIn("notif-popup-ok", html)
        self.assertIn(">OK<", html)
        # Se marca como vista para que no vuelva a saltar sola.
        self.assertFalse(
            Notificacion.objects.filter(
                usuario=self.usuario, mostrada_en__isnull=True
            ).exists()
        )


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class InterruptorGlpiTest(TestCase):
    """El interruptor de GLPI tiene que apagar el bloque en todas las pantallas."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user(
            "jefe@dogger.com.co", "Jefe", "x", rol="admin"
        )
        cls.usuario = User.objects.create_user(
            "persona@dogger.com.co", "Persona", "x", rol="usuario"
        )

    def _apagar(self):
        return self.client.post(
            reverse("accounts:configuracion_pagina"),
            {"ajustes_actividad_glpi": "1", "panel_mostrar_actividad_glpi": "0", "volver": "glpi"},
        )

    def test_el_interruptor_guarda_y_se_ve_apagado(self):
        self.client.force_login(self.admin)
        self._apagar()

        from apps.tickets.models import ConfigSitio

        self.assertFalse(ConfigSitio.cargar().panel_mostrar_actividad_glpi)
        html = self.client.get(reverse("accounts:ajustes")).content.decode()
        self.assertNotIn("Falta aplicar una migración", html)

        # Al guardar se vuelve a la pestaña desde la que se salió el interruptor.
        respuesta = self._apagar()
        self.assertTrue(respuesta.url.endswith(reverse("accounts:ajustes") + "#glpi"))

    def test_guardar_el_interruptor_no_borra_las_redes_sociales(self):
        """El formulario de la pestaña GLPI solo trae el interruptor: no puede
        dejar vacíos los enlaces que se configuraron en la pestaña Página."""
        from apps.tickets.models import ConfigSitio

        cfg = ConfigSitio.cargar()
        cfg.whatsapp_numero = "3103716129"
        cfg.correo_soporte = "soporte@dogger.com.co"
        cfg.tiktok_url = "https://tiktok.com/@dogger"
        cfg.save()

        self.client.force_login(self.admin)
        self._apagar()

        cfg = ConfigSitio.cargar()
        self.assertEqual(cfg.whatsapp_numero, "3103716129")
        self.assertEqual(cfg.correo_soporte, "soporte@dogger.com.co")
        self.assertEqual(cfg.tiktok_url, "https://tiktok.com/@dogger")
        self.assertFalse(cfg.panel_mostrar_actividad_glpi)

    def test_el_bloque_desaparece_del_dashboard_y_de_mi_panel(self):
        self.client.force_login(self.admin)
        self._apagar()

        dashboard = self.client.get(reverse("tickets:dashboard")).content.decode()
        self.assertNotIn("Actividad GLPI", dashboard)

        self.client.force_login(self.usuario)
        mi_panel = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertNotIn("Actividad reciente GLPI", mi_panel)
        self.assertNotIn('id="mini-chat"', mi_panel)

    def test_al_encenderlo_vuelve_a_aparecer(self):
        self.client.force_login(self.admin)
        self._apagar()
        self.client.post(
            reverse("accounts:configuracion_pagina"),
            {"ajustes_actividad_glpi": "1", "panel_mostrar_actividad_glpi": "1", "volver": "glpi"},
        )
        dashboard = self.client.get(reverse("tickets:dashboard")).content.decode()
        self.assertIn("Actividad GLPI", dashboard)


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class EmergenteVerTest(TestCase):
    """"Ver" solo sale cuando hay a dónde ir, y lleva al lugar exacto."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user(
            "jefe@dogger.com.co", "Jefe", "x", rol="admin"
        )

    def test_el_boton_ver_no_aparece_sin_url(self):
        from apps.notificaciones.models import Notificacion

        self.client.force_login(self.admin)
        Notificacion.objects.create(
            usuario=self.admin,
            tipo=Notificacion.Tipo.TICKET_EDITADO,
            titulo="Sin destino",
            mensaje="Aviso de prueba",
        )
        html = self.client.get(reverse("tickets:dashboard")).content.decode()
        self.assertIn("Sin destino", html)
        self.assertNotIn("notif-popup-ver", html)

    def test_el_aviso_de_evento_abre_el_mes_y_el_evento(self):
        import datetime as dt

        from apps.programador.models import CalendarioEvento

        from django.utils import timezone

        manana = timezone.localdate() + dt.timedelta(days=1)
        evento = CalendarioEvento.objects.create(
            fecha=manana,
            hora="08:30",
            titulo="Mantenimiento de red",
            tipo="tarea",
            tecnico=self.admin,
        )
        avisos._recordatorio_eventos(self.admin, dt.date.today())

        from apps.notificaciones.models import Notificacion

        aviso = Notificacion.objects.filter(
            usuario=self.admin, tipo=Notificacion.Tipo.EVENTO
        ).get()
        self.assertIn(f"anio={manana.year}", aviso.url)
        self.assertIn(f"mes={manana.month}", aviso.url)
        self.assertIn(f"ev={evento.pk}", aviso.url)


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class VerAbreTodosLosRecientesTest(TestCase):
    """El "Ver" del aviso de registrados muestra los tickets en la tabla.

    - La URL del aviso pide la página completa de recientes.
    - Al abrirla salen todos los tickets activos, no solo los 6 de la
      primera página.
    - El botón "Ver todos" lleva el badge de En vivo.
    - El JS cierra la emergente inicial al dar clic en Ver/OK.
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user(
            "jefe12@dogger.com.co", "Jefe", "x", rol="admin"
        )

    def _aviso_registrados(self):
        for i in range(12):
            _crear_ticket(f"HD-60{i:02d}")
        avisos.recordatorios(self.admin)
        return Notificacion.objects.get(
            usuario=self.admin, clave__startswith="rec:registrados:"
        )

    def test_la_url_del_aviso_pide_todos_los_recientes(self):
        aviso = self._aviso_registrados()
        self.assertEqual(aviso.titulo, "Se han registrado 12 tickets activos")
        self.assertTrue(
            aviso.url.endswith(reverse("tickets:dashboard") + "?per_page_recientes=0"),
            aviso.url,
        )

    def test_al_abrirla_salen_los_doce_en_la_tabla(self):
        aviso = self._aviso_registrados()
        self.client.force_login(self.admin)
        respuesta = self.client.get(aviso.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["recientes_page"].paginator.count, 12)
        self.assertEqual(len(respuesta.context["recientes"]), 12)
        html = respuesta.content.decode()
        for i in range(12):
            self.assertIn(f"HD-60{i:02d}", html)

    def test_ver_todos_lleva_el_badge_en_vivo(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("tickets:dashboard")).content.decode()
        ver_todos = html.find("Ver todos")
        self.assertNotEqual(ver_todos, -1, "debe existir el botón Ver todos")
        cierre = html.find("</a>", ver_todos)
        badge = html.find("badge-envivo", ver_todos, cierre)
        self.assertNotEqual(badge, -1, "el badge va dentro del botón Ver todos")
        self.assertIn("En vivo", html[ver_todos:cierre])

    def test_el_js_cierra_la_emergente_inicial_al_dar_clic(self):
        from django.contrib.staticfiles import finders

        ruta = finders.find("js/dogger.js")
        self.assertTrue(ruta, "dogger.js debe existir en estáticos")
        with open(ruta, encoding="utf-8") as f:
            js = f.read()
        self.assertIn('querySelectorAll("[data-notif-cerrar]")', js)
