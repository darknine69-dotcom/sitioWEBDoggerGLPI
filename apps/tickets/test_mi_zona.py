"""Mi zona y presionar al técnico: el usuario ve quién lo gobierna."""

import json
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Usuario
from apps.tickets.models import (
    ElementoMiLista,
    ObservadorPunto,
    Punto,
    Ticket,
    TicketComentario,
    ZonaObservador,
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
        self.carpeta_inicial = ZonaObservador.objects.create(observador=self.sup, nombre="Carpeta inicial")
        ElementoMiLista.objects.create(
            observador=self.sup, tipo=ElementoMiLista.TIPO_USUARIO,
            usuario_email="ana@x.com", zona=self.carpeta_inicial,
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
        self.assertIn("Gráficas de tus zonas", html)
        self.assertIn("Ranking de zonas", html)

    def test_muestra_zona_de_seguimiento_y_sus_metricas_solo_con_tickets_propios(self):
        zona = ZonaObservador.objects.create(
            observador=self.sup, nombre="Balcones2"
        )
        elemento = ElementoMiLista.objects.get(
            observador=self.sup, usuario_email="ana@x.com"
        )
        elemento.zona = zona
        elemento.save(update_fields=["zona"])
        Ticket.objects.create(
            titulo="Ticket de otra persona en Balcones2",
            descripcion="d",
            solicitante_nombre="Luis",
            solicitante_email="luis@x.com",
            solicitante_punto="Balcones2",
            tecnico_asignado=self.tec,
        )
        ElementoMiLista.objects.create(
            observador=self.sup,
            tipo=ElementoMiLista.TIPO_USUARIO,
            usuario_email="luis@x.com",
            zona=zona,
        )
        punto_extra = Punto.objects.create(nombre="Punto supervisor no asociado")
        ObservadorPunto.objects.create(observador=self.sup, punto=punto_extra)
        Ticket.objects.create(
            titulo="Ticket de usuario fuera de Balcones2",
            descripcion="d",
            solicitante_nombre="Marta",
            solicitante_email="marta@x.com",
            solicitante_punto="Punto supervisor no asociado",
            tecnico_asignado=self.tec,
        )

        respuesta = self.client.get(reverse("tickets:mi_panel"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.context["mi_zona"]["supervisores"][0]["zona"],
            "Balcones2",
        )
        zonas = respuesta.context["zona_seguimiento_dashboard"]["zonas"]
        self.assertEqual(len(zonas), 1)
        self.assertEqual(zonas[0]["nombre"], "Balcones2")
        self.assertEqual(zonas[0]["total"], 2)
        self.assertEqual(zonas[0]["abiertos"], 2)
        self.assertTrue(zonas[0]["seguimiento"])
        self.assertEqual(
            respuesta.context["zona_indicadores"],
            {
                "zonas": 1,
                "cuentas": 2,
                "tickets": 2,
                "abiertos": 2,
                "en_progreso": 0,
                "vencidos": 0,
            },
        )
        chart_data = json.loads(respuesta.context["dash_json"])
        self.assertEqual(
            sum(row["value"] for row in chart_data["pie_categoria"]["todas"]),
            2,
        )
        html = respuesta.content.decode()
        self.assertIn("Supervisor de", html)
        self.assertIn("Balcones2", html)
        self.assertIn("Fuera de línea", html)
        self.assertIn('class="mz-team-summary"', html)
        self.assertLess(html.index('class="mz-team-summary"'), html.index('class="mz-body"'))
        self.assertNotIn('class="mz-equipo-zonas"', html)
        self.assertIn("Tu zona de seguimiento", html)
        self.assertIn("Gráficas de tus zonas", html)
        self.assertNotIn("Actividad global de tus zonas", html)
        self.assertNotIn("de las cuentas incluidas en tus zonas", html)
        self.assertNotIn('id="mzZonaGrafica"', html)

    def test_al_quitar_usuario_de_zona_no_muestra_su_supervisor(self):
        """Una cuenta sin carpeta activa ya no debe conservar acompañamiento."""
        zona = ZonaObservador.objects.create(
            observador=self.sup, nombre="Zona Azul"
        )
        elemento = ElementoMiLista.objects.get(
            observador=self.sup, usuario_email="ana@x.com"
        )
        elemento.zona = zona
        elemento.save(update_fields=["zona"])

        elemento.zona = None
        elemento.save(update_fields=["zona"])

        respuesta = self.client.get(reverse("tickets:mi_panel"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["mi_zona"]["supervisores"], [])
        self.assertEqual(respuesta.context["mi_zona"]["zonas_seguimiento"], [])

    def test_ranking_y_alertas_usan_carpetas_y_no_puntos_de_venta(self):
        zona = ZonaObservador.objects.create(
            observador=self.sup, nombre="Balcones2"
        )
        ElementoMiLista.objects.filter(
            observador=self.sup, usuario_email="ana@x.com"
        ).update(zona=zona)
        Ticket.objects.create(
            titulo="Solicitud Medellin",
            descripcion="d",
            solicitante_nombre="Ana",
            solicitante_email="ana@x.com",
            solicitante_punto="medellin",
            tecnico_asignado=None,
        )

        respuesta = self.client.get(reverse("tickets:mi_panel"))
        self.assertEqual(respuesta.status_code, 200)
        ranking = respuesta.content.decode().split(
            '<aside class="mz-side">', 1
        )[1].split("Alertas de desempeño", 1)[0]
        alertas = respuesta.content.decode().split(
            "Alertas de desempeño", 1
        )[1].split("</aside>", 1)[0]

        self.assertIn("Balcones2", ranking)
        self.assertNotIn("medellin", ranking)
        self.assertIn("sin asignar en Balcones2", alertas)
        self.assertNotIn("medellin", alertas)
        html = respuesta.content.decode()
        self.assertIn(
            ".mz-team-person { display: flex; flex-direction: row-reverse;",
            html,
        )
        self.assertIn(
            ".mz-team-person .mz-stack-ava { width: 44px; height: 44px;",
            html,
        )

    def test_indicador_ans_vencido_incluye_las_cuentas_de_su_carpeta(self):
        zona = ZonaObservador.objects.create(
            observador=self.sup, nombre="Balcones ANS"
        )
        ElementoMiLista.objects.filter(
            observador=self.sup, usuario_email="ana@x.com"
        ).update(zona=zona)
        ElementoMiLista.objects.create(
            observador=self.sup,
            tipo=ElementoMiLista.TIPO_USUARIO,
            usuario_email="luis@x.com",
            zona=zona,
        )
        vencido = Ticket.objects.create(
            titulo="Caso vencido de otro punto", descripcion="d",
            solicitante_nombre="Luis", solicitante_email="luis@x.com",
            solicitante_punto="Otro punto", tecnico_asignado=self.tec,
        )
        Ticket.objects.filter(pk=vencido.pk).update(
            fecha_creacion=timezone.now() - timedelta(days=30)
        )

        respuesta = self.client.get(reverse("tickets:mi_panel"))

        self.assertEqual(respuesta.context["zona_indicadores"]["vencidos"], 1)

    def test_graficas_usan_datos_globales_de_sus_zonas_sin_selector_de_zona(self):
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
            [("Zona Dos", 1), ("Zona Uno", 1)],
        )

        filtro_ignorado = self.client.get(
            reverse("tickets:mi_panel"),
            {"zona_grafica": "Zona Uno"},
        )
        zona_graficas = json.loads(filtro_ignorado.context["dash_json"])
        self.assertEqual(
            sum(
                fila["value"]
                for fila in zona_graficas["pie_categoria"]["todas"]
            ),
            2,
        )
        self.assertEqual(filtro_ignorado.context["zona_indicadores"]["tickets"], 2)

    def test_tabla_punto_muestra_todos_los_puntos_y_sus_tickets(self):
        punto_dos = Punto.objects.create(nombre="Punto Dos")
        ObservadorPunto.objects.create(observador=self.sup, punto=punto_dos)
        carpeta = ZonaObservador.objects.create(observador=self.sup, nombre="Carpeta asignada")
        ElementoMiLista.objects.filter(observador=self.sup, usuario_email=self.usuario.email).update(zona=carpeta)
        for punto in (self.punto, punto_dos):
            ElementoMiLista.objects.create(observador=self.sup, tipo=ElementoMiLista.TIPO_PUNTO, punto=punto, zona=carpeta)
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

    def test_tabla_punto_cuenta_ans_vencidos_aun_sin_detalle(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(
            fecha_creacion=timezone.now() - timedelta(days=3)
        )

        respuesta = self.client.get(reverse("tickets:mi_panel"))
        pivot_punto = json.loads(respuesta.context["dash_json"])["pivot"]["dimensiones"]["punto"]

        fila = next(fila for fila in pivot_punto["rows"] if fila["label"] == "Zona Uno")
        self.assertEqual(fila["vencido"], 1)
        self.assertEqual(fila["tickets"], [])

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
