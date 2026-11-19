from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test import RequestFactory

from apps.tickets.models import Categoria, ConfiguracionAutoasignacion, DecisionAutoasignacion, PerfilAutoasignacion, Punto, Ticket
from apps.tickets.services.autoasignacion_transaccional import BloqueoAsignacionNoDisponible, asignar_ticket, asignar_manual
from apps.notificaciones.models import AlertaOperativa, HistorialAlerta, Notificacion


class ServicioAsignacionTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(grupo="Pruebas", nombre="Red")
        self.tecnico = get_user_model().objects.create_user("tecnico@example.com", "Técnico", "clave", rol="tecnico")
        self.ticket = Ticket.objects.create(titulo="Prueba", categoria=self.categoria, prioridad="alta")
        ConfiguracionAutoasignacion.objects.create(pk=1, activa=True)
        PerfilAutoasignacion.objects.create(tecnico=self.tecnico, habilitado=True, cobertura_general=True, capacidad=10)

    def test_backend_sin_bloqueo_rechaza(self):
        with patch.object(connection.features, "has_select_for_update", False):
            with self.assertRaises(BloqueoAsignacionNoDisponible):
                asignar_ticket(self.ticket.pk)

    def test_asigna_y_registra_decision(self):
        # Solo comprueba la lógica transaccional en SQLite; no demuestra concurrencia.
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            resultado = asignar_ticket(self.ticket.pk)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.tecnico_asignado_id, self.tecnico.pk)
        self.assertEqual(resultado.motivo, "menor_ocupacion")
        self.assertEqual(DecisionAutoasignacion.objects.filter(ticket=self.ticket).count(), 1)

    def test_error_auditoria_revierte_ticket_y_rotacion(self):
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""), patch.object(DecisionAutoasignacion.objects, "create", side_effect=RuntimeError("error")):
            # using() devuelve un queryset, por lo que se simula el fallo en su create.
            with patch("django.db.models.query.QuerySet.create", side_effect=RuntimeError("error")):
                with self.assertRaises(RuntimeError):
                    asignar_ticket(self.ticket.pk)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.tecnico_asignado_id)
        self.assertEqual(ConfiguracionAutoasignacion.objects.get(pk=1).secuencia, 0)

    def test_asignacion_manual_no_se_sobrescribe(self):
        self.ticket.tecnico_asignado = self.tecnico
        self.ticket.save(update_fields=["tecnico_asignado"])
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            self.assertIsNone(asignar_ticket(self.ticket.pk))
        self.assertFalse(DecisionAutoasignacion.objects.filter(ticket=self.ticket).exists())

    def test_asignacion_manual_confirmada_prevalece(self):
        asignado, cambiado = asignar_manual(self.ticket.pk, self.tecnico)
        self.assertTrue(cambiado)
        self.assertFalse(asignado.asignacion_automatica)
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            self.assertIsNone(asignar_ticket(self.ticket.pk))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.tecnico_asignado_id, self.tecnico.pk)

    def test_tomar_ticket_ya_asignado_no_lo_reemplaza(self):
        otro = get_user_model().objects.create_user("otro@example.com", "Otro", "clave", rol="tecnico")
        asignar_manual(self.ticket.pk, self.tecnico)
        ticket, cambiado = asignar_manual(self.ticket.pk, otro, solo_sin_asignar=True)
        self.assertFalse(cambiado)
        self.assertEqual(ticket.tecnico_asignado_id, self.tecnico.pk)

    def test_desasignacion_manual_tambien_se_respeta(self):
        asignar_manual(self.ticket.pk, None)
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            self.assertIsNone(asignar_ticket(self.ticket.pk))
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.tecnico_asignado_id)
        self.assertTrue(self.ticket.asignacion_manual_protegida)

    def test_eliminar_demo_desasigna_con_proteccion_manual(self):
        from io import StringIO
        from django.core.management import call_command
        asignar_manual(self.ticket.pk, self.tecnico)
        call_command("eliminar_demo", email=self.tecnico.email, stdout=StringIO())
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.tecnico_asignado_id)
        self.assertTrue(self.ticket.asignacion_manual_protegida)

    def test_cierre_y_reapertura_actualizan_la_carga_ponderada(self):
        from apps.tickets.services.transiciones_ans import cambiar_estado_ans
        PerfilAutoasignacion.objects.filter(tecnico=self.tecnico).update(capacidad=3)
        asignar_manual(self.ticket.pk, self.tecnico)
        nuevo = Ticket.objects.create(titulo="Otro", categoria=self.categoria, prioridad="alta")
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            self.assertEqual(asignar_ticket(nuevo.pk).motivo, "capacidad_insuficiente")
            cambiar_estado_ans(self.ticket.pk, Ticket.Estado.CERRADO)
            self.assertEqual(asignar_ticket(nuevo.pk).candidato.pk, self.tecnico.pk)
            cambiar_estado_ans(self.ticket.pk, Ticket.Estado.ABIERTO)
            tercero = Ticket.objects.create(titulo="Tercero", categoria=self.categoria, prioridad="alta")
            self.assertEqual(asignar_ticket(tercero.pk).motivo, "capacidad_insuficiente")

    def test_cambiar_punto_no_sobrescribe_tecnico(self):
        asignar_manual(self.ticket.pk, self.tecnico)
        ticket, _ = asignar_manual(self.ticket.pk, None, cambiar_tecnico=False, cambios={"solicitante_punto": "Norte"})
        self.assertEqual(ticket.tecnico_asignado_id, self.tecnico.pk)
        self.assertEqual(ticket.solicitante_punto, "Norte")

    def test_capacidad_insuficiente_queda_sin_asignar(self):
        PerfilAutoasignacion.objects.filter(tecnico=self.tecnico).update(capacidad=2)
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            resultado = asignar_ticket(self.ticket.pk)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.tecnico_asignado_id)
        self.assertEqual(resultado.motivo, "capacidad_insuficiente")
        self.assertTrue(DecisionAutoasignacion.objects.filter(ticket=self.ticket, motivo="capacidad_insuficiente").exists())
        alerta = AlertaOperativa.objects.get(ticket=self.ticket, tipo="asignacion_pendiente")
        self.assertEqual(alerta.estado, AlertaOperativa.Estado.ABIERTA)

    def test_alerta_saturacion_es_idempotente_y_se_resuelve_al_asignar(self):
        PerfilAutoasignacion.objects.filter(tecnico=self.tecnico).update(capacidad=2)
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            asignar_ticket(self.ticket.pk)
            asignar_ticket(self.ticket.pk)
            alerta = AlertaOperativa.objects.get(ticket=self.ticket, tipo="asignacion_pendiente")
            self.assertEqual(HistorialAlerta.objects.filter(alerta=alerta, accion="creada").count(), 1)
            PerfilAutoasignacion.objects.filter(tecnico=self.tecnico).update(capacidad=10)
            asignar_ticket(self.ticket.pk)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado, AlertaOperativa.Estado.RESUELTA)
        self.assertEqual(HistorialAlerta.objects.filter(alerta=alerta, accion="resuelta").count(), 1)

    def test_asignacion_manual_resuelve_alerta_pendiente(self):
        PerfilAutoasignacion.objects.filter(tecnico=self.tecnico).update(capacidad=2)
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            asignar_ticket(self.ticket.pk)
        asignar_manual(self.ticket.pk, self.tecnico)
        alerta = AlertaOperativa.objects.get(ticket=self.ticket, tipo="asignacion_pendiente")
        self.assertEqual(alerta.estado, AlertaOperativa.Estado.RESUELTA)
        self.assertTrue(HistorialAlerta.objects.filter(alerta=alerta, accion="resuelta").exists())

    def test_alerta_se_entrega_al_admin_sin_duplicados(self):
        admin = get_user_model().objects.create_user("admin-alerta@example.com", "Admin", "clave", rol="admin")
        PerfilAutoasignacion.objects.filter(tecnico=self.tecnico).update(capacidad=2)
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            with self.captureOnCommitCallbacks(execute=True):
                asignar_ticket(self.ticket.pk)
                asignar_ticket(self.ticket.pk)
        avisos = Notificacion.objects.filter(usuario=admin, clave=f"ticket:{self.ticket.pk}:nuevo:{admin.pk}")
        self.assertEqual(avisos.count(), 1)
        self.assertIn("capacidad", avisos.get().mensaje)

    def test_reintento_alerta_es_idempotente(self):
        from io import StringIO
        from django.core.management import call_command
        admin = get_user_model().objects.create_user("retry@example.com", "Admin", "clave", rol="admin")
        PerfilAutoasignacion.objects.filter(tecnico=self.tecnico).update(capacidad=2)
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            asignar_ticket(self.ticket.pk)
        call_command("reenviar_alertas_autoasignacion", stdout=StringIO())
        call_command("reenviar_alertas_autoasignacion", stdout=StringIO())
        self.assertEqual(Notificacion.objects.filter(usuario=admin, clave=f"ticket:{self.ticket.pk}:nuevo:{admin.pk}").count(), 1)

    def test_administracion_no_amplia_acceso_a_staff_no_superusuario(self):
        from django.contrib import admin
        from apps.tickets.admin import PerfilAutoasignacionAdmin
        request = RequestFactory().get("/admin/")
        request.user = self.tecnico
        self.tecnico.is_staff = True
        panel = PerfilAutoasignacionAdmin(PerfilAutoasignacion, admin.site)
        self.assertFalse(panel.has_view_permission(request))
        self.assertFalse(panel.has_change_permission(request))

    def test_formulario_rechaza_pesos_y_margen_invalidos(self):
        from apps.tickets.admin import ConfiguracionAutoasignacionForm
        form = ConfiguracionAutoasignacionForm(data={"peso_urgente": 0, "peso_alta": 3, "peso_media": 2, "peso_baja": 1, "margen_puntos": 101, "secuencia": 0})
        self.assertFalse(form.is_valid())
        self.assertIn("peso_urgente", form.errors)
        self.assertIn("margen_puntos", form.errors)

    def test_cobertura_restringida_excluye_puntos_diferentes(self):
        perfil = PerfilAutoasignacion.objects.get(tecnico=self.tecnico)
        perfil.cobertura_general = False
        perfil.save(update_fields=["cobertura_general"])
        perfil.puntos_cobertura.add(Punto.objects.create(nombre="Norte"))
        self.ticket.solicitante_punto = "Sur"
        self.ticket.save(update_fields=["solicitante_punto"])
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            resultado = asignar_ticket(self.ticket.pk)
        self.assertEqual(resultado.motivo, "sin_candidatos")
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.tecnico_asignado_id)

    def test_cobertura_coincidente_admite_punto(self):
        perfil = PerfilAutoasignacion.objects.get(tecnico=self.tecnico)
        perfil.cobertura_general = False
        perfil.save(update_fields=["cobertura_general"])
        perfil.puntos_cobertura.add(Punto.objects.create(nombre="Norte"))
        self.ticket.solicitante_punto = " norte "
        self.ticket.save(update_fields=["solicitante_punto"])
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            resultado = asignar_ticket(self.ticket.pk)
        self.assertEqual(resultado.candidato.pk, self.tecnico.pk)

    def test_cobertura_restringida_sin_puntos_no_es_general(self):
        PerfilAutoasignacion.objects.filter(tecnico=self.tecnico).update(cobertura_general=False)
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            resultado = asignar_ticket(self.ticket.pk)
        self.assertEqual(resultado.motivo, "sin_candidatos")
