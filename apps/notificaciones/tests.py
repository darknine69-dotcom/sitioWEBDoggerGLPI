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
    def test_clave_reservada_por_usuario_y_liberada_al_borrar(self):
        primero = services.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "Uno", "", clave="estable")
        self.assertIsNone(services.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "Dos", "", clave="estable"))
        self.assertIsNotNone(services.crear(self.usuario, Notificacion.Tipo.SISTEMA, "Otro", "", clave="estable"))
        primero.delete()
        self.assertIsNotNone(services.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "Nuevo", "", clave="estable"))

    def test_base_de_datos_rechaza_reservas_duplicadas(self):
        from django.db import IntegrityError, transaction
        from apps.notificaciones.models import ClaveNotificacion

        primero = services.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "Uno", "", clave="unica")
        segundo = services.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "Dos", "")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClaveNotificacion.objects.create(usuario=self.tecnico, clave="unica", notificacion=segundo)
        self.assertEqual(ClaveNotificacion.objects.get(notificacion=primero).clave, "unica")

    def test_alerta_ans_se_crea_una_vez_con_historial(self):
        from apps.notificaciones.models import AlertaOperativa
        from apps.tickets.ans_avisos import avisos_en_campana
        from django.utils import timezone

        ticket = self.ticket()
        Ticket.objects.filter(pk=ticket.pk).update(fecha_creacion=timezone.now() - timezone.timedelta(days=30))
        ticket.refresh_from_db()
        avisos_en_campana(ticket, "Vencido")
        avisos_en_campana(ticket, "Vencido")
        alerta = AlertaOperativa.objects.get(ticket=ticket)
        self.assertEqual(alerta.estado, AlertaOperativa.Estado.ABIERTA)
        self.assertEqual(alerta.historial.count(), 1)

    def test_bandeja_presenta_inactividad_en_formato_legible(self):
        from django.utils import timezone

        ticket = self.ticket()
        alerta = services.crear_alerta_operativa(f"ticket:{ticket.pk}:inactivo:1", "ticket_inactivo", ticket, self.tecnico)
        alerta.ultima_actividad_en = timezone.now() - timezone.timedelta(hours=3)
        alerta.inactividad_segundos = 12600
        alerta.save(update_fields=["ultima_actividad_en", "inactividad_segundos"])
        self.client.force_login(self.tecnico)
        respuesta = self.client.get(reverse("notificaciones:alertas_operativas"))
        self.assertContains(respuesta, "3h 30min")
        self.assertNotContains(respuesta, "12600 segundos")

    def test_bandeja_conserva_estado_en_selector_y_boton_accesible(self):
        self.client.force_login(self.tecnico)
        respuesta = self.client.get(reverse("notificaciones:alertas_operativas"), {"estado": "reconocida"})
        self.assertContains(respuesta, 'value="reconocida" checked')
        self.assertContains(respuesta, 'aria-label="Aplicar filtro"')
        self.assertContains(respuesta, 'id="estado-alerta-actual">Reconocidas')

    def test_reconocimiento_de_alerta_es_individual_y_controla_acceso(self):
        from apps.notificaciones.models import AlertaOperativa

        ticket = self.ticket()
        alerta = services.crear_alerta_operativa(f"ticket:{ticket.pk}:ans_vencido", "ans_vencido", ticket, self.tecnico)
        otro_tecnico = get_user_model().objects.create_user(email="otro@example.com", password="x", nombre="Otro", rol="tecnico")
        url = reverse("notificaciones:accion_alerta", args=[alerta.pk])
        self.client.force_login(otro_tecnico)
        self.assertEqual(self.client.post(url, {"accion": "reconocer"}).status_code, 404)
        self.client.force_login(self.tecnico)
        self.assertContains(self.client.get(reverse("notificaciones:alertas_operativas")), ticket.codigo)
        self.client.post(url, {"accion": "reconocer"})
        self.client.post(url, {"accion": "reconocer"})
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado, AlertaOperativa.Estado.RECONOCIDA)
        self.assertEqual(alerta.historial.count(), 2)
        respuesta = self.client.get(reverse("notificaciones:alertas_operativas"))
        self.assertContains(respuesta, "Esta alerta ya fue reconocida")
        self.assertContains(respuesta, 'alertas-status is-reconocida')
        self.client.post(url, {"accion": "resolver"})
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado, AlertaOperativa.Estado.RECONOCIDA)
        ticket.estado = Ticket.Estado.RESUELTO
        ticket.save(update_fields=["estado"])
        self.client.post(url, {"accion": "resolver"})
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado, AlertaOperativa.Estado.RESUELTA)

    def test_seguimiento_de_alerta_registra_actor_y_respeta_alcance(self):
        ticket = self.ticket()
        alerta = services.crear_alerta_operativa(f"ticket:{ticket.pk}:ans_vencido", "ans_vencido", ticket, self.tecnico)
        otro = get_user_model().objects.create_user(email="otro-seguimiento@example.com", password="x", nombre="Otro", rol="tecnico")
        url = reverse("notificaciones:accion_alerta", args=[alerta.pk])
        self.client.force_login(otro)
        self.assertEqual(self.client.post(url, {"accion": "seguimiento", "detalle": "No autorizado"}).status_code, 404)
        self.client.force_login(self.tecnico)
        self.client.post(url, {"accion": "seguimiento", "detalle": "Se contactó al punto"})
        entrada = alerta.historial.get(accion="seguimiento")
        self.assertEqual(entrada.actor, self.tecnico)
        self.assertEqual(entrada.detalle, "Se contactó al punto")
        self.assertContains(self.client.get(reverse("notificaciones:alertas_operativas")), "Se contactó al punto")
        self.client.post(url, {"accion": "seguimiento", "detalle": " "})
        self.assertEqual(alerta.historial.filter(accion="seguimiento").count(), 1)

    def test_reconocer_y_cerrar_muestran_confirmacion_sin_cambiar_ticket(self):
        ticket = self.ticket()
        alerta = services.crear_alerta_operativa(f"presion:test:{ticket.pk}", "presion_pendiente", ticket, self.tecnico)
        url = reverse("notificaciones:accion_alerta", args=[alerta.pk])
        self.client.force_login(self.tecnico)
        respuesta = self.client.post(url, {"accion": "reconocer"}, follow=True)
        self.assertContains(respuesta, "Alerta reconocida. El ticket continúa sin cambios.")
        respuesta = self.client.post(url, {"accion": "resolver"}, follow=True)
        self.assertContains(respuesta, "Alerta cerrada correctamente. El ticket no se modificó.")
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, Ticket.Estado.ABIERTO)

    def test_historial_de_alerta_sobrevive_a_eliminacion_del_ticket(self):
        ticket = self.ticket()
        alerta = services.crear_alerta_operativa(f"ticket:{ticket.pk}:ans_vencido", "ans_vencido", ticket, self.tecnico)
        codigo = ticket.codigo
        ticket.delete()
        alerta.refresh_from_db()
        self.assertIsNone(alerta.ticket_id)
        self.assertEqual(alerta.codigo_ticket, codigo)
        self.assertEqual(alerta.historial.count(), 1)

    def test_presion_crea_alerta_idempotente(self):
        from apps.tickets.models import TicketComentario
        from apps.tickets.notifications import notificar_presion_observadores
        from apps.notificaciones.models import AlertaOperativa

        ticket = self.ticket()
        presion = TicketComentario.objects.create(ticket=ticket, usuario=self.usuario, comentario="Solicito seguimiento", es_presion=True)
        notificar_presion_observadores(ticket, self.usuario, presion)
        notificar_presion_observadores(ticket, self.usuario, presion)
        alerta = AlertaOperativa.objects.get(clave_origen=f"presion:{presion.pk}")
        self.assertEqual(alerta.tipo, "presion_pendiente")
        self.assertEqual(alerta.historial.count(), 1)

    def test_inactividad_critica_requiere_umbral_y_se_deduplica(self):
        from apps.notificaciones.models import AlertaOperativa
        from apps.tickets.ans_avisos import _revisar_inactividad
        from django.utils import timezone

        ticket = self.ticket()
        Ticket.objects.filter(pk=ticket.pk).update(fecha_actualizacion=timezone.now() - timezone.timedelta(hours=25))
        _revisar_inactividad()
        _revisar_inactividad()
        self.assertEqual(AlertaOperativa.objects.filter(ticket=ticket, tipo="ticket_inactivo").count(), 1)
        self.assertEqual(AlertaOperativa.objects.get(ticket=ticket, tipo="ticket_inactivo").responsable, self.tecnico)

    def test_revision_cierra_alerta_cuando_ticket_se_resuelve_y_audita_una_vez(self):
        from apps.notificaciones.models import AlertaOperativa
        from apps.tickets.ans_avisos import _revisar_inactividad

        ticket = self.ticket()
        alerta = services.crear_alerta_operativa(f"ticket:{ticket.pk}:ans_vencido", "ans_vencido", ticket, self.tecnico)
        ticket.estado = Ticket.Estado.RESUELTO
        ticket.save(update_fields=["estado"])
        _revisar_inactividad()
        _revisar_inactividad()
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado, AlertaOperativa.Estado.RESUELTA)
        self.assertIsNotNone(alerta.resuelta_en)
        self.assertEqual(alerta.historial.filter(accion="ticket_cerrado").count(), 1)

    def test_escalamiento_desactivado_y_una_sola_vez_por_destinatario(self):
        from apps.tickets.models import ConfigSitio
        from apps.tickets.ans_avisos import _escalar_inactividad
        from apps.notificaciones.models import EntregaEscalamiento
        from django.utils import timezone

        admin = get_user_model().objects.create_user(email="jefe-escalamiento@example.com", password="x", nombre="Jefe", rol="admin")
        ticket = self.ticket()
        alerta = services.crear_alerta_operativa(f"ticket:{ticket.pk}:inactivo:test", "ticket_inactivo", ticket, self.tecnico)
        alerta.ultima_actividad_en = ticket.fecha_actualizacion
        alerta.save(update_fields=["ultima_actividad_en"])
        type(alerta).objects.filter(pk=alerta.pk).update(creada_en=timezone.now() - timezone.timedelta(hours=3))
        _escalar_inactividad()
        self.assertFalse(EntregaEscalamiento.objects.filter(alerta=alerta).exists())
        cfg = ConfigSitio.cargar()
        cfg.escalamiento_inactividad = {"habilitado": True, "horas": 2, "administradores": True, "observadores": False}
        cfg.save(update_fields=["escalamiento_inactividad"])
        _escalar_inactividad()
        _escalar_inactividad()
        self.assertEqual(EntregaEscalamiento.objects.filter(alerta=alerta, usuario=admin).count(), 1)
        self.assertEqual(Notificacion.objects.filter(usuario=admin, clave=f"escalamiento:{alerta.pk}:{admin.pk}").count(), 1)
        self.assertEqual(alerta.historial.filter(accion="escalada").count(), 1)

    def test_escalamiento_no_ocurre_si_hay_seguimiento(self):
        from apps.tickets.models import ConfigSitio
        from apps.tickets.ans_avisos import _escalar_inactividad
        from apps.notificaciones.models import EntregaEscalamiento, HistorialAlerta
        from django.utils import timezone

        get_user_model().objects.create_user(email="jefe-ocupado@example.com", password="x", nombre="Jefe", rol="admin")
        ticket = self.ticket()
        alerta = services.crear_alerta_operativa(f"ticket:{ticket.pk}:inactivo:seguido", "ticket_inactivo", ticket, self.tecnico)
        type(alerta).objects.filter(pk=alerta.pk).update(creada_en=timezone.now() - timezone.timedelta(hours=3), ultima_actividad_en=ticket.fecha_actualizacion)
        HistorialAlerta.objects.create(alerta=alerta, actor=self.tecnico, accion="seguimiento", detalle="Atendiendo")
        cfg = ConfigSitio.cargar()
        cfg.escalamiento_inactividad = {"habilitado": True, "horas": 2, "administradores": True}
        cfg.save(update_fields=["escalamiento_inactividad"])
        _escalar_inactividad()
        self.assertFalse(EntregaEscalamiento.objects.filter(alerta=alerta).exists())

    def test_escalamiento_notifica_tecnico_y_solicitante_sin_duplicados(self):
        from apps.tickets.models import ConfigSitio
        from apps.tickets.ans_avisos import _escalar_inactividad
        from apps.notificaciones.models import EntregaEscalamiento
        from django.utils import timezone

        ticket = self.ticket()
        alerta = services.crear_alerta_operativa(f"ticket:{ticket.pk}:inactivo:destinos", "ticket_inactivo", ticket, self.tecnico)
        type(alerta).objects.filter(pk=alerta.pk).update(creada_en=timezone.now() - timezone.timedelta(hours=3), ultima_actividad_en=ticket.fecha_actualizacion)
        cfg = ConfigSitio.cargar()
        cfg.escalamiento_inactividad = {"habilitado": True, "horas": 2, "tecnico": True, "solicitante": True}
        cfg.save(update_fields=["escalamiento_inactividad"])
        _escalar_inactividad()
        _escalar_inactividad()
        self.assertEqual(EntregaEscalamiento.objects.filter(alerta=alerta).count(), 2)
        aviso_tecnico = Notificacion.objects.get(usuario=self.tecnico, clave=f"escalamiento:{alerta.pk}:{self.tecnico.pk}")
        aviso_usuario = Notificacion.objects.get(usuario=self.usuario, clave=f"escalamiento:{alerta.pk}:{self.usuario.pk}")
        self.assertEqual(aviso_tecnico.url, reverse("tickets:detalle", args=[ticket.pk]))
        self.assertEqual(aviso_usuario.url, reverse("tickets:mi_ticket", args=[ticket.pk]))
        self.assertIn("sigue pendiente", aviso_usuario.titulo)

    def test_escalamiento_observadores_solo_zona_autorizada(self):
        from apps.tickets.models import ConfigSitio, ElementoMiLista, ZonaObservador
        from apps.tickets.ans_avisos import _escalar_inactividad
        from apps.notificaciones.models import EntregaEscalamiento
        from django.utils import timezone

        User = get_user_model()
        autorizado = User.objects.create_user(email="obs-autorizado@example.com", password="x", nombre="Obs", rol="observador")
        ajeno = User.objects.create_user(email="obs-ajeno@example.com", password="x", nombre="Ajeno", rol="observador")
        zona = ZonaObservador.objects.create(observador=autorizado, nombre="Zona", alertas_ans=True)
        ElementoMiLista.objects.create(observador=autorizado, usuario=self.usuario, usuario_email=self.usuario.email, zona=zona)
        ticket = self.ticket()
        alerta = services.crear_alerta_operativa(f"ticket:{ticket.pk}:inactivo:zona", "ticket_inactivo", ticket, self.tecnico)
        type(alerta).objects.filter(pk=alerta.pk).update(creada_en=timezone.now() - timezone.timedelta(hours=3), ultima_actividad_en=ticket.fecha_actualizacion)
        cfg = ConfigSitio.cargar()
        cfg.escalamiento_inactividad = {"habilitado": True, "horas": 2, "observadores": True}
        cfg.save(update_fields=["escalamiento_inactividad"])
        _escalar_inactividad()
        self.assertTrue(EntregaEscalamiento.objects.filter(alerta=alerta, usuario=autorizado).exists())
        self.assertFalse(EntregaEscalamiento.objects.filter(alerta=alerta, usuario=ajeno).exists())

    def test_escalamiento_se_detiene_si_el_ticket_se_actualizo(self):
        from apps.tickets.models import ConfigSitio
        from apps.tickets.ans_avisos import _escalar_inactividad
        from apps.notificaciones.models import EntregaEscalamiento
        from django.utils import timezone

        get_user_model().objects.create_user(email="admin-actividad@example.com", password="x", nombre="Admin", rol="admin")
        ticket = self.ticket()
        alerta = services.crear_alerta_operativa(f"ticket:{ticket.pk}:inactivo:actividad", "ticket_inactivo", ticket, self.tecnico)
        type(alerta).objects.filter(pk=alerta.pk).update(creada_en=timezone.now() - timezone.timedelta(hours=3), ultima_actividad_en=ticket.fecha_actualizacion - timezone.timedelta(minutes=1))
        cfg = ConfigSitio.cargar()
        cfg.escalamiento_inactividad = {"habilitado": True, "horas": 2, "administradores": True}
        cfg.save(update_fields=["escalamiento_inactividad"])
        _escalar_inactividad()
        self.assertFalse(EntregaEscalamiento.objects.filter(alerta=alerta).exists())

    def test_aviso_prioritario_identifica_ans_vencido(self):
        from django.utils import timezone

        vencido = self.ticket(titulo="Ticket vencido")
        vigente = self.ticket(titulo="Ticket vigente")
        Ticket.objects.filter(pk=vencido.pk).update(fecha_creacion=timezone.now() - timezone.timedelta(days=30))
        aviso = next(n for n in services.recordatorios(self.tecnico) if n.clave.startswith("rec:urgentes:"))
        self.assertIn("1 con ANS vencido", aviso.mensaje)
        self.assertIn(vencido.codigo, aviso.mensaje)
        self.assertNotIn(vigente.codigo, aviso.mensaje)

    def test_aviso_prioritario_sin_ans_vencido(self):
        self.ticket()
        aviso = next(n for n in services.recordatorios(self.tecnico) if n.clave.startswith("rec:urgentes:"))
        self.assertIn("Ninguno tiene el ANS vencido", aviso.mensaje)

    def test_aviso_de_prioridad_alta_o_urgente_abre_la_lista_filtrada(self):
        from django.contrib.auth import get_user_model

        admin = get_user_model().objects.create_user(
            email="admin@dogger.com.co",
            password="Admin123!",
            nombre="Admin",
            rol=get_user_model().Rol.ADMIN,
        )
        asignado = self.ticket(titulo="Alta asignado")
        sin_asignar = self.ticket(
            titulo="Urgente sin asignar",
            prioridad=Ticket.Prioridad.URGENTE,
            tecnico_asignado=None,
        )
        self.ticket(titulo="Baja activa", prioridad=Ticket.Prioridad.BAJA)
        cerrada = self.ticket(titulo="Urgente cerrada", prioridad=Ticket.Prioridad.URGENTE)
        cerrada.estado = Ticket.Estado.CERRADO
        cerrada.save(update_fields=["estado"])

        servicios = services.recordatorios(admin)
        aviso = next(n for n in servicios if n.clave.startswith("rec:urgentes:"))
        self.assertEqual(aviso.titulo, "2 tickets de prioridad alta o urgente")
        self.assertEqual(
            aviso.url,
            reverse("tickets:lista") + "?prioridad=alta,urgente#filtrosTickets",
        )

        self.client.force_login(admin)
        respuesta = self.client.get(aviso.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            {ticket.pk for ticket in respuesta.context["tickets"]},
            {asignado.pk, sin_asignar.pk},
        )
        self.assertContains(respuesta, "Alta o urgente")

    def test_aviso_prioritario_del_tecnico_solo_cuenta_sus_tickets(self):
        self.ticket(titulo="Alta asignado al técnico")
        self.ticket(
            titulo="Urgente asignado a otro",
            prioridad=Ticket.Prioridad.URGENTE,
            tecnico_asignado=None,
        )
        aviso = next(
            n for n in services.recordatorios(self.tecnico)
            if n.clave.startswith("rec:urgentes:")
        )

        self.assertEqual(aviso.titulo, "1 ticket de prioridad alta o urgente")
        self.assertEqual(
            aviso.url,
            reverse("tickets:lista") + "?prioridad=alta,urgente#filtrosTickets",
        )

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
    def test_recordatorio_respeta_hora_y_anticipacion_y_oculta_aviso_anterior(self):
        from datetime import datetime, timedelta
        from unittest.mock import patch
        from django.utils import timezone

        inicio = timezone.make_aware(datetime(2026, 10, 30, 1, 4), timezone.get_current_timezone())
        evento = CalendarioEvento.objects.create(tipo=CalendarioEvento.Tipo.RECORDATORIO, titulo="Factura", fecha=inicio.date(), hora=inicio.time(), tecnico=self.tecnico, metadatos={"anticipacion": "30_min"})
        aviso = services.crear(self.tecnico, Notificacion.Tipo.EVENTO, "Recordatorio: Factura", "Programado", clave=f"evento:{evento.pk}:{evento.fecha.isoformat()}")
        with patch("django.utils.timezone.now", return_value=inicio - timedelta(hours=2)):
            self.assertNotIn(aviso, services.pendientes_de_emergente(self.tecnico, limite=10))
            self.assertNotIn(aviso, services.lista(self.tecnico))
            self.assertEqual(services.no_leidas(self.tecnico), 0)
        with patch("django.utils.timezone.now", return_value=inicio - timedelta(minutes=30)):
            self.assertIn(aviso, services.pendientes_de_emergente(self.tecnico, limite=10))

    def test_recordatorio_compartido_se_genera_en_el_momento_configurado(self):
        from datetime import datetime, timedelta
        from unittest.mock import patch
        from django.utils import timezone

        inicio = timezone.make_aware(datetime(2026, 10, 30, 10, 0), timezone.get_current_timezone())
        CalendarioEvento.objects.create(tipo=CalendarioEvento.Tipo.RECORDATORIO, titulo="Compartido", fecha=inicio.date(), hora=inicio.time(), metadatos={"anticipacion": "1_dia", "visibilidad": "todos"})
        with patch("django.utils.timezone.now", return_value=inicio - timedelta(days=1, minutes=1)):
            self.assertEqual([n for n in services.recordatorios(self.tecnico) if n.tipo == Notificacion.Tipo.EVENTO], [])
        with patch("django.utils.timezone.now", return_value=inicio - timedelta(days=1)):
            self.assertTrue(any(n.tipo == Notificacion.Tipo.EVENTO for n in services.recordatorios(self.tecnico)))

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

        # El aviso existe y todavia no se mostro.
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

        # Al cerrarla se marca como mostrada, pero permanece sin leer.
        self.client.post(reverse("notificaciones:marcar_mostrada", args=[aviso.pk]))
        aviso.refresh_from_db()
        self.assertIsNotNone(aviso.mostrada_en)
        self.assertFalse(aviso.leida)

        respuesta = self.client.get(reverse("tickets:panel_tecnico"))
        self.assertNotContains(respuesta, "notifPopup")

    def test_cerrar_y_leer_solo_afecta_al_aviso_elegido(self):
        primero = services.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "Primero", "Uno")
        segundo = services.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "Segundo", "Dos")
        self.client.force_login(self.tecnico)
        respuesta = self.client.post(reverse("notificaciones:marcar_mostrada", args=[primero.pk]))
        self.assertEqual(respuesta.json()["pendientes"], 2)
        primero.refresh_from_db()
        segundo.refresh_from_db()
        self.assertIsNotNone(primero.mostrada_en)
        self.assertFalse(primero.leida)
        self.assertIsNone(segundo.mostrada_en)
        self.assertFalse(segundo.leida)
        respuesta = self.client.post(reverse("notificaciones:marcar_leida", args=[primero.pk]))
        self.assertEqual(respuesta.json()["pendientes"], 1)
        primero.refresh_from_db()
        segundo.refresh_from_db()
        self.assertTrue(primero.leida)
        self.assertIsNotNone(primero.leida_en)
        self.assertFalse(segundo.leida)
        self.assertIsNone(segundo.mostrada_en)

    def test_no_puede_marcar_aviso_de_otra_cuenta(self):
        aviso = services.crear(self.usuario, Notificacion.Tipo.SISTEMA, "Privado", "Otro usuario")
        self.client.force_login(self.tecnico)
        for nombre in ("marcar_mostrada", "marcar_leida"):
            self.assertEqual(self.client.post(reverse("notificaciones:" + nombre, args=[aviso.pk])).status_code, 404)
        aviso.refresh_from_db()
        self.assertFalse(aviso.leida)
        self.assertIsNone(aviso.mostrada_en)

    def test_visitar_panel_no_marca_avisos_como_leidos(self):
        aviso = services.crear(self.tecnico, Notificacion.Tipo.TICKET_NUEVO, "Pendiente", "Aviso")
        self.client.force_login(self.tecnico)
        self.client.get(reverse("tickets:panel_tecnico"))
        aviso.refresh_from_db()
        self.assertFalse(aviso.leida)

    def test_centro_muestra_solo_avisos_propios_y_filtra(self):
        propio = services.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "Aviso propio", "Detalle")
        services.crear(self.usuario, Notificacion.Tipo.SISTEMA, "Aviso privado ajeno", "Detalle")
        self.client.force_login(self.tecnico)
        respuesta = self.client.get(reverse("notificaciones:centro"), {"q": "propio"})
        self.assertContains(respuesta, propio.titulo)
        self.assertNotContains(respuesta, "Aviso privado ajeno")

    def test_centro_impide_accion_sobre_aviso_ajeno(self):
        ajeno = services.crear(self.usuario, Notificacion.Tipo.SISTEMA, "Ajeno", "Detalle")
        self.client.force_login(self.tecnico)
        respuesta = self.client.post(reverse("notificaciones:accion_centro", args=[ajeno.pk]), {"accion": "leer"})
        self.assertEqual(respuesta.status_code, 404)
        ajeno.refresh_from_db()
        self.assertFalse(ajeno.leida)

    def test_archivar_y_restaurar_conserva_lectura_y_contador(self):
        aviso = services.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "Prueba archivo", "Detalle")
        otro = services.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "Otro", "Detalle")
        self.client.force_login(self.tecnico)
        url = reverse("notificaciones:accion_centro", args=[aviso.pk])
        respuesta_archivar = self.client.post(url, {"accion": "archivar"})
        self.assertEqual(respuesta_archivar.url, reverse("notificaciones:centro") + "?filtro=archivadas")
        aviso.refresh_from_db()
        self.assertIsNotNone(aviso.archivada_en)
        self.assertFalse(aviso.leida)
        self.assertEqual(services.no_leidas(self.tecnico), 1)
        self.assertNotIn(aviso, services.lista(self.tecnico))
        self.assertNotIn(aviso, services.pendientes_de_emergente(self.tecnico, limite=10))
        respuesta = self.client.get(reverse("notificaciones:centro"), {"filtro": "archivadas"})
        self.assertContains(respuesta, "Prueba archivo")
        self.assertNotIn(otro, respuesta.context["pagina_avisos"].object_list)
        self.assertContains(respuesta, "Carpetas de notificaciones")
        self.client.post(url, {"accion": "restaurar"})
        aviso.refresh_from_db()
        self.assertIsNone(aviso.archivada_en)
        self.assertEqual(services.no_leidas(self.tecnico), 2)

    def test_centro_no_redirige_a_url_externa(self):
        aviso = services.crear(self.tecnico, Notificacion.Tipo.SISTEMA, "Enlace", "Detalle", url="https://ejemplo-malicioso.invalid/")
        self.client.force_login(self.tecnico)
        respuesta = self.client.post(reverse("notificaciones:accion_centro", args=[aviso.pk]), {"accion": "abrir"})
        self.assertRedirects(respuesta, reverse("notificaciones:centro"))
        aviso.refresh_from_db()
        self.assertFalse(aviso.leida)


@override_settings(STORAGES=STATIC_SIN_MANIFEST)
class FechaNotificacionesTest(TestCase):
    """La campana muestra la fecha y hora pequeñas de cada aviso."""

    def setUp(self):
        User = get_user_model()
        self.tec = User.objects.create_user(
            email="tecf@x.com", password="x", nombre="Tec", rol=User.Rol.TECNICO
        )
        self.client.force_login(self.tec)

    def _aviso(self):
        return services.crear(
            self.tec,
            Notificacion.Tipo.TICKET_NUEVO,
            "Ticket nuevo",
            "Llegó una solicitud.",
            url="/panel/tecnico/?vista=cola",
        )

    def test_la_campana_muestra_fecha_y_hora(self):
        from django.utils import timezone

        aviso = self._aviso()
        esperada = timezone.localtime(aviso.creada_en).strftime("%d/%m/%Y %H:%M")
        html = self.client.get(reverse("tickets:panel_tecnico")).content.decode()
        self.assertIn(esperada, html)
        self.assertIn("notif-time", html)

    def test_la_api_trae_la_fecha(self):
        from django.utils import timezone

        aviso = self._aviso()
        esperada = timezone.localtime(aviso.creada_en).strftime("%d/%m/%Y %H:%M")
        datos = self.client.get(reverse("notificaciones:api")).json()
        self.assertTrue(datos["ok"])
        por_id = {a["id"]: a for a in datos["avisos"]}
        self.assertIn(aviso.pk, por_id)
        self.assertEqual(por_id[aviso.pk]["fecha"], esperada)

    def test_el_js_pinta_la_fecha_que_manda_la_api(self):
        from django.contrib.staticfiles import finders

        ruta = finders.find("js/dogger.js")
        self.assertTrue(ruta, "dogger.js debe existir en estáticos")
        with open(ruta, encoding="utf-8") as f:
            js = f.read()
        self.assertIn('esc(n.fecha || "ahora mismo")', js)

    def test_encabezado_sigue_el_color_personalizado(self):
        from django.contrib.staticfiles import finders

        with open(finders.find("css/dogger-theme.css"), encoding="utf-8") as f:
            css = f.read()
        # Paleta elegida o color propio: el encabezado usa el acento.
        self.assertIn("html[data-navpalette] .notif-head", css)
        self.assertIn('--sb-accent"] .notif-head', css)
        # Sin personalizar sigue negro: la base no usa el acento.
        base = css.split(".notif-head {", 1)[1].split("}", 1)[0]
        self.assertIn("var(--dogger-black)", base)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ActorResponsableTest(BaseNotificaciones):
    def _ticket(self):
        from apps.tickets.models import Ticket

        return Ticket.objects.create(
            titulo="T", descripcion="d", solicitante_nombre="Ana",
            solicitante_email=self.usuario.email, solicitante_punto="X",
            tecnico_asignado=self.tecnico,
        )

    def test_aviso_guarda_quien_genero_el_evento(self):
        from apps.notificaciones import services as srv

        ticket = self._ticket()
        creadas = srv.ticket_editado(ticket, self.tecnico, "Respondio: voy")
        self.assertTrue(creadas)
        for n in creadas:
            self.assertEqual(n.actor, "Tecnico")
            self.assertEqual(n.actor_rol, "Técnico")

    def test_rol_en_popup_y_api(self):
        from apps.notificaciones import services as srv

        ticket = self._ticket()
        srv.ticket_editado(ticket, self.tecnico, "Respondio: voy")
        self.client.force_login(self.usuario)
        datos = self.client.get(reverse("notificaciones:api")).json()
        tecnico = [a for a in datos["avisos"] if a["actor"] == "Tecnico"]
        self.assertTrue(tecnico)
        self.assertEqual(tecnico[0]["actor_rol"], "Técnico")

    def test_api_y_campana_muestran_al_responsable(self):
        from apps.notificaciones import services as srv

        ticket = self._ticket()
        srv.ticket_editado(ticket, self.tecnico, "Respondio: voy")
        self.client.force_login(self.usuario)
        datos = self.client.get(reverse("notificaciones:api")).json()
        actores = [a["actor"] for a in datos["avisos"]]
        self.assertIn("Tecnico", actores)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn("por Tecnico", html)

    def test_toast_pequeno_con_responsable(self):
        from django.contrib.staticfiles import finders

        with open(finders.find("js/dogger.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("toast-actor", js)
        self.assertIn("n.actor", js)
        with open(finders.find("css/dogger-theme.css"), encoding="utf-8") as f:
            css = f.read()
        pila = css.split(".toast-stack")[1].split("}")[0]
        self.assertIn("width: 280px", pila)
