"""Mi zona y presionar al técnico: el usuario ve quién lo gobierna."""

import json

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Usuario
from apps.tickets.models import (
    ElementoMiLista,
    ObservadorPunto,
    Punto,
    Ticket,
    TicketComentario,
)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class MiZonaSupervisorTest(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            email="ana@x.com", password="x", nombre="Ana", rol=Usuario.Rol.USUARIO
        )
        self.tec = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )
        self.sup = Usuario.objects.create_user(
            email="sup@x.com", password="x", nombre="Sup", rol=Usuario.Rol.OBSERVADOR
        )
        self.punto = Punto.objects.create(nombre="Zona Uno")
        ObservadorPunto.objects.create(observador=self.sup, punto=self.punto)
        ElementoMiLista.objects.create(
            observador=self.sup, tipo=ElementoMiLista.TIPO_USUARIO,
            usuario_email="ana@x.com",
        )
        self.ticket = Ticket.objects.create(
            titulo="Impresora", descripcion="d", solicitante_nombre="Ana",
            solicitante_email="ana@x.com", solicitante_punto="Zona Uno",
            tecnico_asignado=self.tec,
        )
        self.client.force_login(self.usuario)

    def test_mi_panel_muestra_zona_y_supervisor(self):
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn("Mi zona y supervisor", html)
        self.assertIn("Zona Uno", html)
        self.assertIn("Sup", html)
        self.assertIn("Presionar", html)
        self.assertIn(self.ticket.codigo, html)

    def test_presionar_crea_comentario_y_avisa(self):
        respuesta = self.client.post(
            reverse("tickets:mi_presionar", args=[self.ticket.pk]),
            {"mensaje": "Ayuda por favor"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(
            TicketComentario.objects.filter(
                ticket=self.ticket, comentario="Ayuda por favor",
                es_interno=False).exists())

    def test_presionar_ajeno_da_404(self):
        ajeno = Ticket.objects.create(
            titulo="Otro", descripcion="d", solicitante_nombre="Luis",
            solicitante_email="luis@x.com", tecnico_asignado=self.tec,
        )
        self.assertEqual(
            self.client.post(
                reverse("tickets:mi_presionar", args=[ajeno.pk]),
                {"mensaje": "Hola"}).status_code, 404)
        self.assertFalse(TicketComentario.objects.filter(ticket=ajeno).exists())

    def test_presionar_sin_mensaje_ni_tecnico_falla(self):
        self.assertEqual(
            self.client.post(
                reverse("tickets:mi_presionar", args=[self.ticket.pk]),
                {"mensaje": "  "}).status_code, 302)
        self.assertFalse(TicketComentario.objects.filter(ticket=self.ticket).exists())
        self.ticket.tecnico_asignado = None
        self.ticket.save()
        self.assertEqual(
            self.client.post(
                reverse("tickets:mi_presionar", args=[self.ticket.pk]),
                {"mensaje": "Hola"}).status_code, 302)
        self.assertFalse(TicketComentario.objects.filter(ticket=self.ticket).exists())

    def test_dashboard_de_zona_con_metricas(self):
        respuesta = self.client.get(reverse("tickets:mi_panel"))
        self.assertEqual(respuesta.status_code, 200)
        zd = respuesta.context["zona_dashboard"]
        self.assertEqual(len(zd["zonas"]), 1)
        zona = zd["zonas"][0]
        self.assertEqual(zona["nombre"], "Zona Uno")
        self.assertEqual(zona["total"], 1)
        self.assertEqual(zona["abiertos"], 1)
        self.assertEqual(zona["posicion"], 1)
        datos = respuesta.context["zona_datos"]
        self.assertEqual(datos["barras"]["labels"], ["Zona Uno"])
        self.assertEqual(datos["barras"]["abiertos"], [1])
        self.assertEqual(datos["categorias"]["labels"], ["Sin categoría"])
        graficas = json.loads(respuesta.context["dash_json"])
        self.assertIsNotNone(graficas["pivot"])
        punto_pivot = graficas["pivot"]["dimensiones"]["punto"]
        self.assertEqual(punto_pivot["label"], "Punto de venta")
        self.assertEqual(
            [(fila["label"], fila["total"]) for fila in punto_pivot["rows"]],
            [("Zona Uno", 1)],
        )
        self.assertTrue(punto_pivot["aggregate_only"])
        self.assertEqual(punto_pivot["rows"][0]["tickets"], [])
        self.assertIn("todas", graficas["pie_categoria"])
        self.assertIn("por_prioridad", graficas["sla"])
        html = respuesta.content.decode()
        self.assertIn('id="dashData"', html)
        self.assertIn('data-widget="categoria"', html)
        self.assertIn('value="punto" selected>Punto de venta</option>', html)
        self.assertLess(
            html.index('data-widget="categoria"'),
            html.index('data-pivot-card'),
        )
        self.assertIn('data-widget="prioridad"', html)
        self.assertIn('data-widget="linea"', html)
        self.assertIn('data-widget="comp20"', html)
        self.assertIn('data-widget="sla"', html)
        self.assertIn("Todos mis tickets", html)
        self.assertIn("Ranking de zonas", html)

    def test_graficas_se_pueden_filtrar_por_zona_y_solo_usan_tickets_propios(self):
        Ticket.objects.create(
            titulo="Otro ticket de Ana",
            descripcion="d",
            solicitante_nombre="Ana",
            solicitante_email="ana@x.com",
            solicitante_punto="Zona Dos",
            tecnico_asignado=self.tec,
        )
        Ticket.objects.create(
            titulo="Ticket ajeno",
            descripcion="d",
            solicitante_nombre="Luis",
            solicitante_email="luis@x.com",
            solicitante_punto="Zona Uno",
            tecnico_asignado=self.tec,
        )

        todas = self.client.get(reverse("tickets:mi_panel"))
        todas_graficas = json.loads(todas.context["dash_json"])
        self.assertEqual(
            sum(
                fila["value"]
                for fila in todas_graficas["pie_categoria"]["todas"]
            ),
            2,
        )
        self.assertEqual(
            [(fila["label"], fila["total"]) for fila in
             todas_graficas["pivot"]["dimensiones"]["punto"]["rows"]],
            [("Zona Uno", 2)],
        )

        zona = self.client.get(
            reverse("tickets:mi_panel"),
            {"zona_grafica": "Zona Uno"},
        )
        zona_graficas = json.loads(zona.context["dash_json"])
        self.assertEqual(zona.context["zona_grafica"], "Zona Uno")
        self.assertEqual(
            sum(
                fila["value"]
                for fila in zona_graficas["pie_categoria"]["todas"]
            ),
            1,
        )
        self.assertEqual(zona.context["zona_grafica_total"], 1)

    def test_tabla_punto_muestra_todos_los_puntos_y_sus_tickets(self):
        punto_dos = Punto.objects.create(nombre="Punto Dos")
        ObservadorPunto.objects.create(observador=self.sup, punto=punto_dos)
        Ticket.objects.create(
            titulo="Solicitud de otra persona",
            descripcion="d",
            solicitante_nombre="Luis",
            solicitante_email="luis@x.com",
            solicitante_punto="Zona Uno",
            tecnico_asignado=self.tec,
        )
        Ticket.objects.create(
            titulo="Solicitud en otro punto",
            descripcion="d",
            solicitante_nombre="Luis",
            solicitante_email="luis@x.com",
            solicitante_punto="Punto Dos",
            tecnico_asignado=self.tec,
            estado=Ticket.Estado.CERRADO,
        )
        Ticket.objects.create(
            titulo="Punto fuera de la zona",
            descripcion="d",
            solicitante_nombre="Luis",
            solicitante_email="luis@x.com",
            solicitante_punto="Punto Ajeno",
            tecnico_asignado=self.tec,
        )

        respuesta = self.client.get(reverse("tickets:mi_panel"))
        pivot_punto = json.loads(respuesta.context["dash_json"])["pivot"]["dimensiones"]["punto"]

        self.assertEqual(
            [(fila["label"], fila["total"]) for fila in pivot_punto["rows"]],
            [("Punto Dos", 1), ("Zona Uno", 2)],
        )
        self.assertEqual(pivot_punto["rows"][0]["cerrado"], 1)
        self.assertTrue(all(not fila["tickets"] for fila in pivot_punto["rows"]))

    def test_presionar_zona_avisa_supervisores(self):
        from apps.notificaciones.models import Notificacion

        respuesta = self.client.post(
            reverse("tickets:mi_presionar_zona"),
            {"zona": "Zona Uno", "mensaje": "Ayuda en la zona"})
        self.assertEqual(respuesta.status_code, 302)
        aviso = Notificacion.objects.get(
            usuario=self.sup, titulo__icontains="Zona Uno"
        )
        self.assertEqual(
            aviso.url,
            f"{reverse('tickets:obs_monitoreo')}#zonas",
        )

    def test_presionar_zona_lleva_al_admin_a_sus_zonas(self):
        from apps.notificaciones.models import Notificacion

        admin = Usuario.objects.create_user(
            email="admin@x.com",
            password="admin-password",
            nombre="Admin",
            rol=Usuario.Rol.ADMIN,
        )
        self.punto.observadores.all().delete()

        respuesta = self.client.post(
            reverse("tickets:mi_presionar_zona"),
            {"zona": "Zona Uno", "mensaje": "Ayuda en la zona"},
        )

        self.assertEqual(respuesta.status_code, 302)
        aviso = Notificacion.objects.get(usuario=admin)
        self.assertEqual(
            aviso.url,
            f"{reverse('tickets:monitoreo_admin')}#zonas",
        )

    def test_presionar_zona_ajena_da_404(self):
        from apps.notificaciones.models import Notificacion

        respuesta = self.client.post(
            reverse("tickets:mi_presionar_zona"),
            {"zona": "Zona Ajena", "mensaje": "Hola"})
        self.assertEqual(respuesta.status_code, 404)
        self.assertFalse(Notificacion.objects.filter(
            titulo__icontains="Zona Ajena").exists())
