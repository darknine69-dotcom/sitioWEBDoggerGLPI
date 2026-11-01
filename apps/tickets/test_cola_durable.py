import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.mail import send_mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import ResetPasswordToken, Usuario
from apps.tickets.models import TareaDiferida, Ticket
from apps.tickets.services.cola_durable import encolar, procesar_una
from apps.tickets.services.fondo import en_fondo
from apps.tickets.services.glpi_client import sync_followup_to_glpi


class ColaDurableTest(TestCase):
    def _correo(self):
        return encolar(send_mail, ("Asunto", "codigo-secreto-123", "origen@example.test", ["destino@example.test"]), {"html_message": "<p>Hola</p>"})

    def test_datos_en_bd_estan_cifrados_y_se_borran_tras_entrega(self):
        tarea = self._correo()
        with connection.cursor() as cursor:
            cursor.execute("SELECT datos FROM " + connection.ops.quote_name(TareaDiferida._meta.db_table) + " WHERE id = %s", [tarea.pk])
            datos_guardados = cursor.fetchone()[0]
        self.assertNotIn("codigo-secreto-123", datos_guardados)
        with patch("apps.tickets.services.cola_durable.send_mail", return_value=1) as enviar:
            self.assertEqual(procesar_una(), tarea.pk)
        self.assertFalse(enviar.call_args.kwargs["fail_silently"])
        tarea.refresh_from_db()
        self.assertEqual(tarea.estado, TareaDiferida.Estado.COMPLETADA)
        self.assertEqual(tarea.datos, "")
        self.assertIsNone(procesar_una())
        self.assertEqual(enviar.call_count, 1)

    def test_error_no_se_repite_automaticamente_y_requiere_confirmacion(self):
        tarea = self._correo()
        with patch("apps.tickets.services.cola_durable.send_mail", side_effect=OSError("detalle privado")), self.assertLogs("apps.tickets.services.cola_durable", level="ERROR") as logs:
            procesar_una()
        tarea.refresh_from_db()
        self.assertEqual(tarea.estado, TareaDiferida.Estado.REVISAR)
        self.assertEqual(tarea.ultimo_error, "OSError")
        self.assertNotIn("detalle privado", " ".join(logs.output))
        self.assertIsNone(procesar_una())
        with self.assertRaises(CommandError):
            call_command("procesar_tareas", reintentar=tarea.pk, stdout=StringIO())
        call_command("procesar_tareas", reintentar=tarea.pk, confirmar=True, stdout=StringIO())
        tarea.refresh_from_db()
        self.assertEqual(tarea.estado, TareaDiferida.Estado.PENDIENTE)

    def test_encolado_participa_en_la_transaccion(self):
        try:
            with transaction.atomic():
                self._correo()
                raise ValueError("rollback")
        except ValueError:
            pass
        self.assertFalse(TareaDiferida.objects.exists())

    def test_no_se_permiten_funciones_arbitrarias(self):
        with self.assertRaises(ValueError):
            encolar(lambda: None, (), {})
        self.assertFalse(TareaDiferida.objects.exists())

    @override_settings(DOGGER_FONDO_ASINCRONO=True, DOGGER_FONDO_DURABLE=True)
    def test_modo_durable_no_crea_un_hilo(self):
        with patch("apps.tickets.services.fondo.en_pruebas", return_value=False):
            tarea = en_fondo(send_mail, "Asunto", "Texto", "de@example.test", ["para@example.test"])
        self.assertEqual(tarea.estado, TareaDiferida.Estado.PENDIENTE)
        self.assertEqual(json.loads(tarea.datos)["texto"], "Texto")

    def test_seguimiento_glpi_usa_ticket_existente(self):
        ticket = Ticket.objects.create(titulo="Caso", descripcion="Detalle", solicitante_nombre="A", solicitante_email="a@example.test")
        tarea = encolar(sync_followup_to_glpi, (ticket, "Seguimiento"), {})
        with patch("apps.tickets.services.cola_durable.sync_followup_to_glpi", return_value=True) as enviar:
            procesar_una()
        self.assertEqual(enviar.call_args.args[0].pk, ticket.pk)
        tarea.refresh_from_db()
        self.assertEqual(tarea.estado, TareaDiferida.Estado.COMPLETADA)

    def test_reserva_abandonada_exige_revision_explicita(self):
        tarea = self._correo()
        TareaDiferida.objects.filter(pk=tarea.pk).update(estado=TareaDiferida.Estado.PROCESANDO, reservado_en=timezone.now() - timedelta(minutes=11))
        with self.assertRaises(CommandError):
            call_command("procesar_tareas", marcar_estancada=tarea.pk, stdout=StringIO())
        call_command("procesar_tareas", marcar_estancada=tarea.pk, confirmar=True, stdout=StringIO())
        tarea.refresh_from_db()
        self.assertEqual(tarea.estado, TareaDiferida.Estado.REVISAR)
        self.assertIsNone(procesar_una())

    def test_codigo_reset_vencido_o_reemplazado_no_se_envia(self):
        usuario = Usuario.objects.create_user(email="reset@example.test", password="secreta", nombre="Prueba", rol=Usuario.Rol.USUARIO)
        for modo in ("vencido", "reemplazado", "usado"):
            with self.subTest(modo=modo):
                token = ResetPasswordToken.generar(usuario)
                tarea = encolar(send_mail, ("Reset", token.codigo, "de@example.test", [usuario.email]), {}, reset_token_id=token.pk)
                if modo == "vencido":
                    ResetPasswordToken.objects.filter(pk=token.pk).update(creado=timezone.now() - timedelta(minutes=31))
                elif modo == "reemplazado":
                    ResetPasswordToken.generar(usuario)
                else:
                    ResetPasswordToken.objects.filter(pk=token.pk).update(usado=True)
                with patch("apps.tickets.services.cola_durable.send_mail") as enviar:
                    procesar_una()
                    enviar.assert_not_called()
                tarea.refresh_from_db()
                self.assertEqual(tarea.estado, TareaDiferida.Estado.FALLIDA)
                self.assertEqual(tarea.datos, "")
                with self.assertRaises(CommandError):
                    call_command("procesar_tareas", reintentar=tarea.pk, confirmar=True, stdout=StringIO())

    def test_codigo_reset_vigente_se_envia(self):
        usuario = Usuario.objects.create_user(email="reset@example.test", password="secreta", nombre="Prueba", rol=Usuario.Rol.USUARIO)
        token = ResetPasswordToken.generar(usuario)
        tarea = encolar(send_mail, ("Reset", token.codigo, "de@example.test", [usuario.email]), {}, reset_token_id=token.pk)
        with patch("apps.tickets.services.cola_durable.send_mail", return_value=1) as enviar:
            procesar_una()
        enviar.assert_called_once()
        tarea.refresh_from_db()
        self.assertEqual(tarea.estado, TareaDiferida.Estado.COMPLETADA)
