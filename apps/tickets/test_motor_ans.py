from datetime import datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils import timezone

from apps.tickets.services.motor_ans import calcular_ans


class MotorANSTest(SimpleTestCase):
    def setUp(self):
        self.inicio = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
        self.ticket = SimpleNamespace(
            ans_verificacion="verificado", ans_inicio_original=self.inicio,
            ans_limite_original=self.inicio + timedelta(hours=12),
            fecha_limite_ans=self.inicio + timedelta(hours=12),
            fecha_creacion=self.inicio, fecha_finalizacion=None,
            estado="abierto", Estado=SimpleNamespace(RESUELTO="resuelto", CERRADO="cerrado"),
        )

    def test_estados_y_limite_exacto(self):
        self.assertEqual(calcular_ans(self.ticket, ahora=self.inicio).estado, "vigente")
        self.assertEqual(calcular_ans(self.ticket, ahora=self.inicio + timedelta(hours=10)).estado, "por_vencer")
        self.assertEqual(calcular_ans(self.ticket, ahora=self.ticket.fecha_limite_ans).estado, "vencido")
        self.assertEqual(calcular_ans(self.ticket, ahora=self.inicio + timedelta(hours=13)).incumplimiento, timedelta(hours=1))

    def test_resolucion_y_cierre_al_limite_y_despues(self):
        for estado in ("resuelto", "cerrado"):
            self.ticket.estado = estado
            self.ticket.fecha_finalizacion = self.ticket.fecha_limite_ans
            self.assertEqual(calcular_ans(self.ticket, ahora=self.inicio).estado, "cumplido")
            self.ticket.fecha_finalizacion += timedelta(seconds=1)
            self.assertEqual(calcular_ans(self.ticket, ahora=self.inicio).estado, "incumplido")

    def test_reapertura_reanuda_plazo_original(self):
        self.ticket.estado = "abierto"
        self.ticket.fecha_finalizacion = self.inicio + timedelta(hours=1)
        self.assertEqual(calcular_ans(self.ticket, ahora=self.inicio + timedelta(hours=13)).estado, "vencido")

    def test_historico_desconocido_y_provisional(self):
        self.ticket.ans_verificacion = "desconocido"
        self.assertEqual(calcular_ans(self.ticket, ahora=self.inicio).estado, "sin_informacion")
        resultado = calcular_ans(self.ticket, ahora=self.inicio, permitir_provisional=True)
        self.assertTrue(resultado.provisional)
        self.assertEqual(resultado.estado, "vigente")

    def test_ajuste_y_zona_horaria(self):
        self.ticket.fecha_limite_ans = self.inicio + timedelta(hours=24)
        resultado = calcular_ans(self.ticket, ahora=self.inicio + timedelta(hours=12))
        self.assertEqual(resultado.porcentaje, 50)
        otra_zona = dt_timezone(timedelta(hours=-5))
        self.assertEqual(resultado, calcular_ans(self.ticket, ahora=(self.inicio + timedelta(hours=12)).astimezone(otra_zona)))

    def test_umbral_configurable_no_cambia_limite(self):
        resultado = calcular_ans(self.ticket, ahora=self.inicio + timedelta(hours=9), umbral=timedelta(hours=4))
        self.assertEqual(resultado.estado, "por_vencer")
        self.assertEqual(resultado.limite, self.ticket.ans_limite_original)

    def test_rechaza_fechas_sin_zona(self):
        with self.assertRaises(ValueError):
            calcular_ans(self.ticket, ahora=datetime(2026, 1, 1))

    def test_ajustes_antes_y_despues_de_resolver_o_cerrar(self):
        original = self.ticket.ans_limite_original
        extendido = original + timedelta(hours=6)
        posterior = extendido + timedelta(hours=6)
        ajustes = [
            SimpleNamespace(version=1, limite_anterior=original, limite_nuevo=extendido,
                            creado_en=self.inicio + timedelta(hours=2)),
            SimpleNamespace(version=2, limite_anterior=extendido, limite_nuevo=posterior,
                            creado_en=self.inicio + timedelta(hours=16)),
        ]
        self.ticket.ans_version_ajuste = 2
        self.ticket.ajustes_ans = SimpleNamespace(order_by=lambda *args: ajustes)
        self.ticket.fecha_limite_ans = posterior
        for estado in ("resuelto", "cerrado"):
            self.ticket.estado = estado
            self.ticket.fecha_finalizacion = self.inicio + timedelta(hours=15)
            resultado = calcular_ans(self.ticket, ahora=self.inicio)
            self.assertEqual(resultado.limite, extendido)
            self.assertEqual(resultado.estado, "cumplido")
            self.ticket.fecha_finalizacion = self.inicio + timedelta(hours=19)
            self.assertEqual(calcular_ans(self.ticket, ahora=self.inicio).limite, posterior)
        self.ticket.estado = "abierto"
        self.assertEqual(calcular_ans(self.ticket, ahora=self.inicio + timedelta(hours=20)).limite, posterior)

    def test_orden_ambiguo_o_cadena_incompleta_no_afirma_cumplimiento(self):
        original = self.ticket.ans_limite_original
        self.ticket.estado = "resuelto"
        self.ticket.fecha_finalizacion = self.inicio + timedelta(hours=10)
        self.ticket.ans_version_ajuste = 1
        ajuste = SimpleNamespace(version=1, limite_anterior=original, limite_nuevo=original + timedelta(hours=2),
                                 creado_en=self.ticket.fecha_finalizacion)
        self.ticket.ajustes_ans = SimpleNamespace(order_by=lambda *args: [ajuste])
        self.assertEqual(calcular_ans(self.ticket, ahora=self.inicio).estado, "sin_informacion")
        self.ticket.ans_version_ajuste = 2
        self.assertEqual(calcular_ans(self.ticket, ahora=self.inicio).estado, "sin_informacion")
