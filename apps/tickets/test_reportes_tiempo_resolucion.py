from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.tickets.models import Categoria, Ticket
from apps.tickets.views import _reportes_filtros, _reportes_metricas_usuarios


class TiempoResolucionUsuariosTests(TestCase):
    def setUp(self):
        self.inicio = timezone.now() - timedelta(days=10)

    def ticket(self, email, nombre="Ana", horas=None, estado=Ticket.Estado.CERRADO, inicio=None):
        inicio = inicio or self.inicio
        ticket = Ticket.objects.create(
            titulo="Incidencia", solicitante_nombre=nombre, solicitante_email=email,
            estado=estado, fecha_resolucion=inicio + timedelta(hours=horas) if horas is not None else None,
        )
        Ticket.objects.filter(pk=ticket.pk).update(fecha_creacion=inicio)
        ticket.refresh_from_db()
        return ticket

    def test_promedio_horas_y_minutos_excluye_cierre_directo(self):
        tickets = [self.ticket("ana@example.com", horas=1.5), self.ticket("ana@example.com", horas=2.5),
                   self.ticket("ana@example.com", horas=None)]
        fila = _reportes_metricas_usuarios(tickets)[0]
        self.assertEqual(fila["prom_h"], 2.0)
        self.assertEqual(fila["n_cerrados"], 2)
        self.assertEqual(fila["creados"], 3)

    def test_usuarios_con_mismo_nombre_se_separan_y_correo_se_normaliza(self):
        get_user_model().objects.create_user("ANA@example.com", "Ana", "clave", rol="usuario")
        tickets = [self.ticket("ana@example.com", horas=1), self.ticket("ANA@example.com", nombre="Ana Pérez", horas=3),
                   self.ticket("otra@example.com", nombre="Ana", horas=10)]
        filas = _reportes_metricas_usuarios(tickets)
        self.assertEqual(len(filas), 2)
        ana = next(fila for fila in filas if fila["email"].lower() == "ana@example.com")
        self.assertEqual(ana["prom_h"], 2)
        self.assertIsNotNone(ana["pk"])

    def test_duplicados_y_fechas_invalidas_no_distorsionan_promedio(self):
        valido = self.ticket("ana@example.com", horas=0)
        invalido = self.ticket("ana@example.com", horas=-2)
        fila = _reportes_metricas_usuarios([valido, valido, invalido])[0]
        self.assertEqual(fila["creados"], 2)
        self.assertEqual(fila["prom_h"], 0)
        self.assertEqual(fila["n_cerrados"], 1)

    def test_tiempo_largo_valido_no_se_descarta(self):
        fila = _reportes_metricas_usuarios([self.ticket("ana@example.com", horas=700.5)])[0]
        self.assertEqual(fila["prom_h"], 700.5)

    def test_filtros_limitan_tickets_por_fecha_de_creacion_y_usuario(self):
        incluido = self.ticket("ana@example.com", horas=1.5)
        self.ticket("ana@example.com", horas=20, inicio=self.inicio - timedelta(days=10))
        self.ticket("otra@example.com", horas=30)
        request = RequestFactory().get("/reportes/", {"desde": timezone.localtime(self.inicio).date().isoformat(), "usuario": "ana@example.com"})
        _, queryset = _reportes_filtros(request)
        self.assertEqual(list(queryset.values_list("pk", flat=True)), [incluido.pk])
        self.assertEqual(_reportes_metricas_usuarios(queryset)[0]["prom_h"], 1.5)

    def test_filtros_de_categoria_prioridad_y_tecnico_se_respetan(self):
        categoria = Categoria.objects.create(grupo="TI", nombre="Red")
        tecnico = get_user_model().objects.create_user("tec@example.com", "Técnico", "clave", rol="tecnico")
        incluido = self.ticket("ana@example.com", horas=1.25)
        excluido = self.ticket("ana@example.com", horas=30)
        Ticket.objects.filter(pk=incluido.pk).update(categoria=categoria, prioridad="alta", tecnico_asignado=tecnico)
        Ticket.objects.filter(pk=excluido.pk).update(categoria=categoria, prioridad="baja", tecnico_asignado=tecnico)
        request = RequestFactory().get("/reportes/", {"categoria": categoria.pk, "prioridad": "alta", "tecnico": tecnico.pk})
        _, queryset = _reportes_filtros(request)
        self.assertEqual(_reportes_metricas_usuarios(queryset)[0]["prom_h"], 1.25)
