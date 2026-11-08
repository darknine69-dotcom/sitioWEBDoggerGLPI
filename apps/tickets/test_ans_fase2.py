from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, Client
from django.test import override_settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from io import StringIO
from django.urls import reverse

from apps.tickets.models import Categoria, Ticket
from apps.tickets.services.transiciones_ans import cambiar_estado_ans, crear_tickets_ans, ajustar_plazo_ans, EstadoTicketModificado
from django.core.exceptions import PermissionDenied


class PersistenciaANSFase2Test(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(grupo="Test", nombre="Original", ans_horas=8)
        self.ticket = Ticket.objects.create(titulo="Test", descripcion="Test", solicitante_nombre="Test",
                                            categoria=self.categoria, prioridad="alta")

    def test_instantanea_no_cambia_al_editar_categoria_o_prioridad(self):
        limite = self.ticket.fecha_limite_ans
        self.assertEqual(limite, self.ticket.fecha_creacion + timedelta(hours=8))
        self.assertEqual(self.ticket.ans_verificacion, "verificado")
        self.categoria.ans_horas = 48
        self.categoria.save()
        self.ticket.prioridad = "urgente"
        self.ticket.categoria = None
        self.ticket.save()
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.fecha_limite_ans, limite)
        self.assertEqual(self.ticket.ans_horas, 8)
        self.assertEqual(self.ticket.ans_categoria_original_id, self.categoria.pk)

    def test_ajuste_autorizado_conserva_original_y_es_idempotente(self):
        admin = get_user_model().objects.create_user(email="admin@example.com", nombre="Admin", password="x", rol="admin")
        original = self.ticket.ans_limite_original
        nuevo = original + timedelta(hours=2)
        args = {"actor": admin, "motivo": "Corrección", "clave": "ajuste-unico", "version_esperada": 0}
        primero = ajustar_plazo_ans(self.ticket.pk, nuevo, **args)
        segundo = ajustar_plazo_ans(self.ticket.pk, nuevo, **args)
        self.assertEqual(primero.pk, segundo.pk)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.ans_limite_original, original)
        self.assertEqual(self.ticket.fecha_limite_ans, nuevo)
        self.assertEqual(primero.limite_anterior, original)
        with self.assertRaises(EstadoTicketModificado):
            ajustar_plazo_ans(self.ticket.pk, nuevo + timedelta(hours=1), actor=admin, motivo="Otro", clave="otro", version_esperada=0)

    def test_ajuste_sin_permiso_rechazado(self):
        tec = get_user_model().objects.create_user(email="tec2@example.com", nombre="Técnico", password="x", rol="tecnico")
        with self.assertRaises(PermissionDenied):
            ajustar_plazo_ans(self.ticket.pk, self.ticket.fecha_limite_ans, actor=tec, motivo="No autorizado", clave="test", version_esperada=0)

    def test_endpoint_ajuste_solo_admin_y_registra_historial(self):
        admin = get_user_model().objects.create_user(email="admin2@example.com", nombre="Admin", password="x", rol="admin")
        tecnico = get_user_model().objects.create_user(email="tec3@example.com", nombre="Técnico", password="x", rol="tecnico")
        url = reverse("tickets:ajustar_ans_ticket", args=[self.ticket.pk])
        datos = {"limite": "2026-12-01T10:00", "motivo": "Revisión", "clave": "endpoint-test", "version": "0"}
        self.client.force_login(tecnico)
        self.assertEqual(self.client.post(url, datos).status_code, 403)
        self.client.force_login(admin)
        self.assertEqual(self.client.post(url, datos).status_code, 302)
        self.assertEqual(self.ticket.ajustes_ans.count(), 1)

    def test_endpoint_ajuste_rechaza_post_sin_csrf(self):
        admin = get_user_model().objects.create_user(email="csrf@example.com", nombre="Admin", password="x", rol="admin")
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(admin)
        respuesta = cliente.post(reverse("tickets:ajustar_ans_ticket", args=[self.ticket.pk]), {})
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(self.ticket.ajustes_ans.exists())

    def test_resolucion_reapertura_y_resolucion_posterior(self):
        t = cambiar_estado_ans(self.ticket.pk, Ticket.Estado.RESUELTO, resolver_y_cerrar=True)
        t = cambiar_estado_ans(t.pk, Ticket.Estado.ABIERTO, estado_esperado=Ticket.Estado.CERRADO)
        self.assertIsNone(t.fecha_resolucion)
        cambiar_estado_ans(t.pk, Ticket.Estado.RESUELTO, resolver_y_cerrar=True)
        eventos = list(t.transiciones_ans.values_list("tipo", "ciclo"))
        self.assertEqual(eventos, [("resolucion", 1), ("cierre", 1), ("reapertura", 2), ("resolucion", 2), ("cierre", 2)])

    def test_estado_obsoleto_no_genera_evento(self):
        cambiar_estado_ans(self.ticket.pk, Ticket.Estado.CERRADO)
        with self.assertRaises(EstadoTicketModificado):
            cambiar_estado_ans(self.ticket.pk, Ticket.Estado.EN_PROGRESO, estado_esperado=Ticket.Estado.ABIERTO)
        self.assertEqual(self.ticket.transiciones_ans.count(), 1)

    def test_reintento_del_mismo_cierre_no_duplica_eventos(self):
        cambiar_estado_ans(self.ticket.pk, Ticket.Estado.CERRADO)
        cambiar_estado_ans(self.ticket.pk, Ticket.Estado.CERRADO)
        self.assertEqual(self.ticket.transiciones_ans.count(), 1)

    def test_bulk_create_no_omite_instantanea(self):
        with self.assertRaises(NotImplementedError):
            Ticket.objects.bulk_create([Ticket(titulo="Sin instantánea")])

    def test_update_directo_de_estado_se_rechaza(self):
        with self.assertRaisesMessage(ValueError, "servicio transaccional ANS"):
            Ticket.objects.filter(pk=self.ticket.pk).update(estado=Ticket.Estado.CERRADO)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.estado, Ticket.Estado.ABIERTO)

    def test_save_directo_de_estado_se_rechaza(self):
        self.ticket.estado = Ticket.Estado.CERRADO
        with self.assertRaisesMessage(ValueError, "requieren el servicio ANS"):
            self.ticket.save()
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.estado, Ticket.Estado.ABIERTO)

    def test_save_no_puede_modificar_instantanea(self):
        self.ticket.ans_limite_original += timedelta(hours=2)
        with self.assertRaisesMessage(ValueError, "instantánea ANS"):
            self.ticket.save(update_fields=["ans_limite_original"])

    def test_save_no_protegido_sigue_permitido(self):
        self.ticket.titulo = "Otro título"
        self.ticket.save(update_fields=["titulo"])
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.titulo, "Otro título")

    def test_bulk_update_de_estado_se_rechaza(self):
        self.ticket.estado = Ticket.Estado.CERRADO
        with self.assertRaisesMessage(ValueError, "servicio transaccional ANS"):
            Ticket.objects.bulk_update([self.ticket], ["estado"])

    def test_update_de_campos_ans_y_fechas_rechazado(self):
        valores = {"fecha_resolucion": None, "fecha_cierre": None,
                   "ans_limite_original": None, "ans_inicio_original": None,
                   "ans_duracion_original": 1, "ans_prioridad_original": "baja",
                   "ans_categoria_original": "otra", "ans_fuente_original": "prioridad"}
        for campo, valor in valores.items():
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                Ticket.objects.filter(pk=self.ticket.pk).update(**{campo: valor})

    def test_creacion_lote_segura_aplica_instantaneas(self):
        tickets = [Ticket(titulo="Lote", descripcion="Prueba", solicitante_nombre="Ana", prioridad="urgente")]
        creado = crear_tickets_ans(tickets)[0]
        self.assertEqual(creado.ans_duracion_original, 2)
        self.assertEqual(creado.ans_verificacion, "verificado")

    def test_error_creando_evento_revierte_estado(self):
        with patch("apps.tickets.services.transiciones_ans.TicketTransicionANS.objects.create", side_effect=RuntimeError("fallo")):
            with self.assertRaises(RuntimeError):
                cambiar_estado_ans(self.ticket.pk, Ticket.Estado.CERRADO)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.estado, Ticket.Estado.ABIERTO)
        self.assertEqual(self.ticket.transiciones_ans.count(), 0)

    @override_settings(DEBUG=False)
    def test_seed_prohibido_fuera_de_debug(self):
        with self.assertRaises(CommandError):
            call_command("seed_prueba", permitir_demo=True, stdout=StringIO())

    @override_settings(DEBUG=True)
    def test_seed_requiere_confirmacion(self):
        with self.assertRaises(CommandError):
            call_command("seed_prueba", stdout=StringIO())

    @override_settings(DEBUG=True)
    def test_seed_crea_instantaneas_coherentes(self):
        get_user_model().objects.create_user(email="tecnico@example.com", nombre="Técnico", password="x", rol="tecnico")
        call_command("seed_prueba", permitir_demo=True, stdout=StringIO())
        tickets = Ticket.objects.filter(solicitante_email__endswith="@dogger.com.co")
        self.assertEqual(tickets.count(), 6)
        for t in tickets:
            self.assertEqual(t.ans_inicio_original, t.fecha_creacion)
            self.assertEqual(t.ans_limite_original, t.fecha_creacion + timedelta(hours=t.ans_duracion_original))

    def test_historico_sin_instantanea_permanece_desconocido(self):
        from django.db.models import QuerySet
        QuerySet.update(Ticket.objects.filter(pk=self.ticket.pk), ans_limite_original=None, ans_duracion_original=None, ans_verificacion="desconocido")
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.ans_verificacion, "desconocido")
        self.assertIsNone(self.ticket.ans_limite_original)
        self.assertIsNotNone(self.ticket.fecha_limite_ans)
