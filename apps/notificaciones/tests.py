"""Pruebas de la campana de notificaciones, la ventana emergente y los correos."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.notificaciones import services
from apps.notificaciones.models import Notificacion
from apps.programador.models import CalendarioEvento
from apps.tickets.models import Categoria, Ticket

STATIC_SIN_MANIFEST = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(
    STORAGES=STATIC_SIN_MANIFEST,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_HOST_USER="soporte@dogger.com.co",
    DEFAULT_FROM_EMAIL="soporte@dogger.com.co",
)
class BaseNotificaciones(TestCase):
    def setUp(self):
        User = get_user_model()
        self.tecnico = User.objects.create_user(
            email="tec@dogger.com.co", password="x", nombre="Tecnico Uno", rol=User.Rol.TECNICO
        )
        self.usuario = User.objects.create_user(
            email="ana@dogger.com.co", password="x", nombre="Ana Ruiz", rol=User.Rol.USUARIO
        )
        self.categoria = Categoria.objects.create(grupo="Hardware", nombre="Portátil")
        # El saludo de primer ingreso no debe ensuciar estas pruebas.
        Notificacion.objects.all().delete()
        from django.utils import timezone

        ya_visto = timezone.now() - timezone.timedelta(days=1)
        self.tecnico.bienvenida_vista = ya_visto
        self.tecnico.save()
        self.usuario.bienvenida_vista = ya_visto
        self.usuario.save()

    def ticket(self, **kwargs):
        datos = {
            "titulo": "No enciende el portátil",
            "descripcion": "Al conectar el cargador no prende.",
            "prioridad": Ticket.Prioridad.ALTA,
            "categoria": self.categoria,
            "solicitante_nombre": "Ana Ruiz",
            "solicitante_email": "ana@dogger.com.co",
            "tecnico_asignado": self.tecnico,
        }
        datos.update(kwargs)
        return Ticket.objects.create(**datos)


class BienvenidaTest(BaseNotificaciones):
    def test_primer_ingreso_crea_aviso_y_correo(self):
        from django.core import mail

        User = get_user_model()
        nuevo = User.objects.create_user(
            email="nuevo@dogger.com.co", password="x", nombre="Nuevo Usuario"
        )
        self.client.force_login(nuevo)

        aviso = Notificacion.objects.get(usuario=nuevo)
        self.assertEqual(aviso.tipo, Notificacion.Tipo.BIENVENIDA)
        self.assertEqual(aviso.icono, "i-star")
        self.assertTrue(aviso.url)
        self.assertIn("Nuevo", aviso.titulo)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Bienvenido", mail.outbox[0].subject)
        self.assertIn("nuevo@dogger.com.co", mail.outbox[0].to)
        self.assertIsNotNone(nuevo.bienvenida_vista)

    def test_no_repite_el_bienvenida_en_el_siguiente_ingreso(self):
        from django.core import mail

        self.usuario.bienvenida_vista = None
        self.usuario.save()
        self.client.force_login(self.usuario)
        mail.outbox.clear()
        self.client.get(reverse("tickets:mi_panel"))

        self.assertEqual(
            Notificacion.objects.filter(usuario=self.usuario, tipo=Notificacion.Tipo.BIENVENIDA).count(),
            1,
        )
        self.assertEqual(len(mail.outbox), 0)


class TicketCreadoTest(BaseNotificaciones):
    def test_avisa_al_tecnico_con_icono_y_enlace(self):
        from apps.tickets.notifications import notificar_ticket_creado

        ticket = self.ticket()
        notificar_ticket_creado(ticket)

        aviso = Notificacion.objects.get(usuario=self.tecnico)
        self.assertEqual(aviso.tipo, Notificacion.Tipo.TICKET_NUEVO)
        self.assertEqual(aviso.icono, "i-inbox")
        self.assertIn(ticket.codigo, aviso.titulo)
        self.assertEqual(aviso.url, reverse("tickets:detalle", args=[ticket.pk]))

    def test_avisa_al_usuario_que_reporto(self):
        from apps.tickets.notifications import notificar_ticket_creado

        ticket = self.ticket(tecnico_asignado=None)
        notificar_ticket_creado(ticket)

        aviso = Notificacion.objects.get(usuario=self.usuario)
        self.assertEqual(aviso.tipo, Notificacion.Tipo.TICKET_NUEVO)
        self.assertIn(ticket.codigo, aviso.titulo)
        self.assertEqual(aviso.url, reverse("tickets:mi_ticket", args=[ticket.pk]))

    def test_correo_al_tecnico_y_al_usuario(self):
        from django.core import mail

        from apps.tickets.notifications import notificar_ticket_creado

        notificar_ticket_creado(self.ticket())
        correos = {c.to[0]: c for c in mail.outbox}

        self.assertIn("tec@dogger.com.co", correos)
        self.assertIn("ana@dogger.com.co", correos)
        self.assertIn("HD-", correos["tec@dogger.com.co"].subject)
        # El correo al técnico va con diseño HTML.
        self.assertIn("<html", correos["tec@dogger.com.co"].alternatives[0][0])

    def test_sin_asignar_avisa_a_todo_el_personal(self):
        from apps.tickets.notifications import notificar_ticket_creado

        get_user_model().objects.create_user(
            email="otro@dogger.com.co", password="x", nombre="Otro Tec", rol="tecnico"
        )
        notificar_ticket_creado(self.ticket(tecnico_asignado=None))

        self.assertEqual(Notificacion.objects.filter(tipo=Notificacion.Tipo.TICKET_NUEVO).count(), 3)

    def test_no_duplica_el_aviso_del_mismo_ticket(self):
        from apps.tickets.notifications import notificar_ticket_creado

        ticket = self.ticket()
        notificar_ticket_creado(ticket)
        notificar_ticket_creado(ticket)

        self.assertEqual(Notificacion.objects.filter(tipo=Notificacion.Tipo.TICKET_NUEVO).count(), 2)


class TicketCerradoTest(BaseNotificaciones):
    def test_avisa_y_correa_al_cerrar(self):
        from django.core import mail

        from apps.tickets.notifications import notificar_ticket_actualizado

        ticket = self.ticket()
        ticket.estado = Ticket.Estado.CERRADO
        ticket.save()
        notificar_ticket_actualizado(ticket, "cambiado a Cerrado", actor=self.tecnico)

        aviso = Notificacion.objects.get(usuario=self.usuario, tipo=Notificacion.Tipo.TICKET_CERRADO)
        self.assertEqual(aviso.icono, "i-check-circle")
        self.assertIn(ticket.codigo, aviso.titulo)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("fue cerrado", mail.outbox[0].subject)
        self.assertIn("ana@dogger.com.co", mail.outbox[0].to)
        self.assertIsNotNone(ticket.fecha_cierre)


class RecordatoriosTest(BaseNotificaciones):
    def test_tecnico_con_ticket_activo(self):
        self.ticket()
        nuevas = services.recordatorios(self.tecnico)

        self.assertTrue(nuevas)
        tipos = {n.tipo for n in nuevas}
        self.assertIn(Notificacion.Tipo.TICKET_RECORDATORIO, tipos)
        aviso = [n for n in nuevas if n.tipo == Notificacion.Tipo.TICKET_RECORDATORIO][0]
        self.assertEqual(aviso.icono, "i-clock")
        self.assertEqual(aviso.url, reverse("tickets:panel_tecnico"))

    def test_no_repite_el_recordatorio_del_dia(self):
        self.ticket()
        services.recordatorios(self.tecnico)
        self.assertEqual(services.recordatorios(self.tecnico), [])

    def test_usuario_ve_sus_tickets_en_curso(self):
        self.ticket()
        nuevas = services.recordatorios(self.usuario)

        self.assertEqual(len(nuevas), 1)
        self.assertEqual(nuevas[0].url, reverse("tickets:mi_panel"))

    def test_ticket_cerrado_no_genera_recordatorio(self):
        self.ticket(estado=Ticket.Estado.CERRADO)
        self.assertEqual(services.recordatorios(self.usuario), [])

    def test_el_conteo_se_actualiza_al_cerrar_un_ticket(self):
        """El número del recordatorio nunca puede quedar desfasado."""
        primero = self.ticket()
        segundo = self.ticket(titulo="WiFi intermitente en el piso 3")

        servicios = services.recordatorios(self.tecnico)
        aviso = [n for n in servicios if n.url == reverse("tickets:panel_tecnico")][0]
        self.assertEqual(aviso.titulo, "Tienes 2 tickets activos")

        # Se cierra uno: el aviso del día debe decir 1, no 2.
        segundo.estado = Ticket.Estado.CERRADO
        segundo.save(update_fields=["estado"])

        services.recordatorios(self.tecnico)
        aviso.refresh_from_db()
        self.assertEqual(aviso.titulo, "Tienes 1 ticket activo")

        # Se cierran todos: el aviso desaparece en vez de mentir con "0".
        primero.estado = Ticket.Estado.CERRADO
        primero.save(update_fields=["estado"])

        services.recordatorios(self.tecnico)
        self.assertFalse(
            Notificacion.objects.filter(clave__startswith="rec:asignados:").exists()
        )

    def test_el_conteo_no_duplica_avisos_al_repetir(self):
        self.ticket()
        services.recordatorios(self.tecnico)
        services.recordatorios(self.tecnico)

        self.assertEqual(
            Notificacion.objects.filter(clave__startswith="rec:asignados:").count(),
            1,
        )


class EventoCalendarioTest(BaseNotificaciones):
    def test_tarea_de_hoy_avisa_con_icono_de_calendario(self):
        from datetime import timedelta

        from django.utils import timezone

        CalendarioEvento.objects.create(
            tipo=CalendarioEvento.Tipo.TAREA,
            titulo="Revisar respaldo del servidor",
            fecha=timezone.localdate(),
            hora="09:00",
            tecnico=self.tecnico,
        )
        nuevas = services.recordatorios(self.tecnico)
        evento = [n for n in nuevas if n.tipo == Notificacion.Tipo.EVENTO]

        self.assertEqual(len(evento), 1)
        self.assertEqual(evento[0].icono, "i-calendar")
        self.assertIn("Revisar respaldo", evento[0].titulo)
        self.assertIn("hoy", evento[0].mensaje)

    def test_evento_terminado_no_avisa(self):
        from django.utils import timezone

        CalendarioEvento.objects.create(
            tipo=CalendarioEvento.Tipo.RECORDATORIO,
            titulo="Tarea vieja",
            fecha=timezone.localdate() - timezone.timedelta(days=5),
            tecnico=self.tecnico,
            completado=True,
        )
        self.assertEqual(
            [n for n in services.recordatorios(self.tecnico) if n.tipo == Notificacion.Tipo.EVENTO],
            [],
        )


class PanelTest(BaseNotificaciones):
    def test_la_campana_aparece_con_el_contador(self):
        self.client.force_login(self.tecnico)
        servicios = services.recordatorios(self.tecnico)
        respuesta = self.client.get(reverse("tickets:panel_tecnico"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "notifBell")
        self.assertContains(respuesta, f">{len(servicios)}<")

    def test_la_campana_no_aparece_a_visitantes(self):
        respuesta = self.client.get(reverse("tickets:portal"))
        self.assertNotContains(respuesta, "notifBell")

    def test_la_x_quita_solo_el_aviso_de_ese_usuario(self):
        aviso = services.crear(
            self.tecnico, Notificacion.Tipo.SISTEMA, "Prueba", "Mensaje de prueba", clave="k1"
        )
        otro = services.crear(self.usuario, Notificacion.Tipo.SISTEMA, "Otro", "Otro", clave="k1")
        self.client.force_login(self.tecnico)

        self.client.post(reverse("notificaciones:descartar_una", args=[aviso.pk]))

        self.assertFalse(Notificacion.objects.filter(pk=aviso.pk).exists())
        self.assertTrue(Notificacion.objects.filter(pk=otro.pk).exists())

    def test_marcar_todas_deja_el_contador_en_cero(self):
        services.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "A", "a", clave="k1")
        services.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "B", "b", clave="k2")
        self.client.force_login(self.tecnico)

        self.client.post(reverse("notificaciones:marcar_todas"))

        self.assertEqual(services.no_leidas(self.tecnico), 0)

    def test_el_enlace_del_aviso_lleva_al_ticket(self):
        ticket = self.ticket()
        servicios = services.ticket_creado(ticket)
        self.client.force_login(self.tecnico)

        respuesta = self.client.get(reverse("tickets:panel_tecnico"))

        self.assertContains(respuesta, reverse("tickets:detalle", args=[ticket.pk]))
        self.assertTrue(any(n.pk == servicios[0].pk for n in servicios))


class VentanaEmergenteTest(BaseNotificaciones):
    def test_salta_la_emergente_y_no_vuelve_a_saltar(self):
        from apps.notificaciones import services as srv

        # El aviso existe y todavía no se mostró.
        aviso = Notificacion.objects.create(
            usuario=self.tecnico,
            tipo=Notificacion.Tipo.TICKET_NUEVO,
            titulo="Nuevo ticket HD-0001",
            mensaje="ALTA · algo falló",
            icono="i-inbox",
            url="/panel/",
        )
        self.client.force_login(self.tecnico)
        respuesta = self.client.get(reverse("tickets:panel_tecnico"))
        self.assertContains(respuesta, "notifPopup")

        # Al cerrarla se marca como mostrada y leída.
        self.client.post(reverse("notificaciones:marcar_mostrada", args=[aviso.pk]))
        aviso.refresh_from_db()
        self.assertIsNotNone(aviso.mostrada_en)
        self.assertTrue(aviso.leida)

        respuesta = self.client.get(reverse("tickets:panel_tecnico"))
        self.assertNotContains(respuesta, "notifPopup")

    def test_solo_muestra_la_mas_reciente(self):
        from apps.notificaciones import services as srv

        srv.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "Viejo", "viejo", clave="a")
        srv.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "Nuevo", "nuevo", clave="b")
        self.client.force_login(self.tecnico)

        respuesta = self.client.get(reverse("tickets:panel_tecnico"))

        self.assertContains(respuesta, "Nuevo")
        self.assertEqual(len(srv.pendientes_de_emergente(self.tecnico, limite=1)), 1)
