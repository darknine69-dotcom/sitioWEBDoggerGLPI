"""Monitoreo por zonas: el admin ve y administra lo que creó cada supervisor."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Usuario
from apps.tickets.models import (
    ElementoMiLista,
    ObservadorPunto,
    Punto,
    Ticket,
    ZonaObservador,
)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class MonitoreoZonasAdminTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="admin@x.com", password="x", nombre="Admin", rol=Usuario.Rol.ADMIN
        )
        self.obs = Usuario.objects.create_user(
            email="obs@x.com", password="x", nombre="Sup", rol=Usuario.Rol.OBSERVADOR
        )
        self.tec = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )
        self.cuenta = Usuario.objects.create_user(
            email="ana@x.com", password="x", nombre="Ana",
            rol=Usuario.Rol.USUARIO, ubicacion="Zona Uno",
        )
        self.punto = Punto.objects.create(nombre="Zona Uno")
        ObservadorPunto.objects.create(observador=self.obs, punto=self.punto)
        self.zona = ZonaObservador.objects.create(
            observador=self.obs, nombre="Norte"
        )
        self.elemento = ElementoMiLista.objects.create(
            observador=self.obs, tipo=ElementoMiLista.TIPO_USUARIO,
            usuario=self.cuenta, usuario_email="ana@x.com", zona=self.zona,
        )
        Ticket.objects.create(
            titulo="T", descripcion="d", solicitante_nombre="Ana",
            solicitante_email="ana@x.com", solicitante_punto="Zona Uno",
            tecnico_asignado=self.tec,
        )
        self.client.force_login(self.admin)

    def test_ve_zonas_agrupadas_por_supervisor(self):
        respuesta = self.client.get(reverse("tickets:monitoreo_admin"))
        self.assertEqual(respuesta.status_code, 200)
        bloques = respuesta.context["zonas_creadas"]
        self.assertEqual(len(bloques), 1)
        self.assertEqual(bloques[0]["supervisor"].email, "obs@x.com")
        self.assertEqual(bloques[0]["zonas"][0]["zona"].nombre, "Norte")
        miembro = bloques[0]["zonas"][0]["miembros"][0]
        self.assertEqual(miembro["email"], "ana@x.com")
        self.assertEqual(miembro["abiertos"], 1)
        self.assertEqual(miembro["tecnico"], "Tec")
        html = respuesta.content.decode()
        self.assertIn("Zonas creadas por los observadores", html)
        self.assertIn("Supervisor a cargo", html)
        self.assertIn("ana@x.com", html)
        dash = respuesta.context["dash"]
        self.assertEqual(dash["supervisores"], 1)
        self.assertEqual(dash["zonas"], 1)
        self.assertEqual(dash["cuentas"], 1)
        self.assertEqual(dash["abiertos"], 1)

    def test_sin_zonas_muestra_aviso(self):
        self.zona.delete()
        html = self.client.get(reverse("tickets:monitoreo_admin")).content.decode()
        self.assertIn("Ningún observador ha creado zonas todavía", html)

    def test_sacar_cuenta_de_la_zona(self):
        respuesta = self.client.post(
            reverse("tickets:monitoreo_zona_miembro_quitar", args=[self.elemento.pk]),
            {"volver": reverse("tickets:monitoreo_admin")},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.elemento.refresh_from_db()
        self.assertIsNone(self.elemento.zona)
        # La cuenta sigue en la lista del observador.
        self.assertTrue(
            ElementoMiLista.objects.filter(pk=self.elemento.pk).exists()
        )

    def test_eliminar_zona_no_borra_la_gente(self):
        respuesta = self.client.post(
            reverse("tickets:monitoreo_zona_eliminar", args=[self.zona.pk]),
            {"volver": reverse("tickets:monitoreo_admin")},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(ZonaObservador.objects.filter(pk=self.zona.pk).exists())
        self.assertTrue(
            ElementoMiLista.objects.filter(pk=self.elemento.pk).exists()
        )

    def test_no_admin_no_administra(self):
        self.client.force_login(self.cuenta)
        self.assertEqual(
            self.client.post(
                reverse("tickets:monitoreo_zona_eliminar", args=[self.zona.pk])
            ).status_code, 403,
        )
        self.assertEqual(
            self.client.post(
                reverse(
                    "tickets:monitoreo_zona_miembro_quitar", args=[self.elemento.pk]
                )
            ).status_code, 403,
        )

    def test_crear_zona_para_supervisor(self):
        respuesta = self.client.post(
            reverse("tickets:monitoreo_zona_crear"),
            {"observador": self.obs.pk, "nombre": "Sur"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(
            ZonaObservador.objects.filter(
                observador=self.obs, nombre="Sur"
            ).exists()
        )

    def test_crear_zona_exige_nombre_y_no_duplica(self):
        respuesta = self.client.post(
            reverse("tickets:monitoreo_zona_crear"),
            {"observador": self.obs.pk, "nombre": "  "},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(ZonaObservador.objects.filter(observador=self.obs).count(), 1)
        self.client.post(
            reverse("tickets:monitoreo_zona_crear"),
            {"observador": self.obs.pk, "nombre": "norte"},
        )
        self.assertEqual(ZonaObservador.objects.filter(observador=self.obs).count(), 1)

    def test_asignar_cuenta_a_la_zona(self):
        respuesta = self.client.post(
            reverse("tickets:monitoreo_zona_miembro_agregar", args=[self.zona.pk]),
            {"email": "nuevo@x.com"},
        )
        self.assertEqual(respuesta.status_code, 302)
        nuevo = ElementoMiLista.objects.get(
            observador=self.obs, usuario_email="nuevo@x.com"
        )
        self.assertEqual(nuevo.zona_id, self.zona.pk)

    def test_ficha_cuenta_con_todo_el_detalle(self):
        from apps.tickets.models import TicketAdjunto, TicketComentario

        ticket = Ticket.objects.get(solicitante_email="ana@x.com")
        TicketComentario.objects.create(
            ticket=ticket, usuario=self.tec, comentario="Ya voy en camino"
        )
        respuesta = self.client.get(
            reverse("tickets:monitoreo_cuenta_detalle", args=[self.elemento.pk])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["total"], 1)
        self.assertEqual(respuesta.context["tecnicos"], [("Tec", 1)])
        html = respuesta.content.decode()
        self.assertIn(ticket.codigo, html)
        self.assertIn("Ya voy en camino", html)
        self.assertIn("Tec", html)

    def test_ficha_cuenta_inexistente_404(self):
        self.assertEqual(
            self.client.get(
                reverse("tickets:monitoreo_cuenta_detalle", args=[999999])
            ).status_code, 404,
        )

    def test_renombrar_zona(self):
        respuesta = self.client.post(
            reverse("tickets:monitoreo_zona_renombrar", args=[self.zona.pk]),
            {"nombre": "Centro"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.zona.refresh_from_db()
        self.assertEqual(self.zona.nombre, "Centro")

    def test_renombrar_zona_no_duplica(self):
        ZonaObservador.objects.create(observador=self.obs, nombre="Sur")
        self.client.post(
            reverse("tickets:monitoreo_zona_renombrar", args=[self.zona.pk]),
            {"nombre": "sur"},
        )
        self.zona.refresh_from_db()
        self.assertEqual(self.zona.nombre, "Norte")

    def test_auditoria_registra_cambios_y_se_ve(self):
        from apps.tickets.models import MonitoreoAuditoria

        self.client.post(
            reverse("tickets:monitoreo_zona_crear"),
            {"observador": self.obs.pk, "nombre": "Sur"},
        )
        self.client.post(
            reverse("tickets:monitoreo_zona_miembro_agregar", args=[self.zona.pk]),
            {"email": "nuevo@x.com"},
        )
        acciones = set(
            MonitoreoAuditoria.objects.values_list("accion", flat=True)
        )
        self.assertIn("crear_zona", acciones)
        self.assertIn("agregar_miembro", acciones)
        html = self.client.get(reverse("tickets:monitoreo_admin")).content.decode()
        self.assertIn("Registro de auditoría", html)
        self.assertIn("Sur", html)

    def test_fab_en_admin_y_supervisor(self):
        html_admin = self.client.get(
            reverse("tickets:monitoreo_admin")
        ).content.decode()
        self.assertIn("fabMonitoreo", html_admin)
        self.assertIn("Generar reporte", html_admin)
        self.client.force_login(self.obs)
        html_obs = self.client.get(
            reverse("tickets:obs_zonas")
        ).content.decode()
        self.assertIn("fabObs", html_obs)
        self.assertIn("Tickets de mis zonas", html_obs)

    def test_supervisor_renombra_su_zona(self):
        self.client.force_login(self.obs)
        respuesta = self.client.post(
            reverse("tickets:obs_zonas"),
            {"zona_id": self.zona.pk, "nuevo_nombre": "Centro"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.zona.refresh_from_db()
        self.assertEqual(self.zona.nombre, "Centro")


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class MonitoreoObservadorDetalleTest(TestCase):
    def setUp(self):
        self.obs = Usuario.objects.create_user(
            email="obs@x.com", password="x", nombre="Obs", rol=Usuario.Rol.OBSERVADOR
        )
        self.tec = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )
        punto = Punto.objects.create(nombre="Zona Uno")
        ObservadorPunto.objects.create(observador=self.obs, punto=punto)
        self.client.force_login(self.obs)

    def _ticket(self, email, punto="Zona Uno", estado=None):
        return Ticket.objects.create(
            titulo="T", descripcion="d", solicitante_nombre="Ana",
            solicitante_email=email, solicitante_punto=punto,
            estado=estado or Ticket.Estado.ABIERTO, tecnico_asignado=self.tec,
        )

    def test_agrupa_por_zona_con_detalle(self):
        from apps.tickets.models import ZonaObservador
        self._ticket("ana@x.com")
        self.client.post(reverse("tickets:obs_agregar"), {"email": "ana@x.com"})
        zona = ZonaObservador.objects.create(observador=self.obs, nombre="Norte")
        elemento = ElementoMiLista.objects.get(observador=self.obs)
        elemento.zona = zona
        elemento.save()
        respuesta = self.client.get(reverse("tickets:obs_monitoreo"))
        self.assertEqual(respuesta.status_code, 200)
        grupos = respuesta.context["grupos"]
        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0]["zona"].nombre, "Norte")
        self.assertEqual(grupos[0]["filas"][0]["tecnico"], "Tec")
        html = respuesta.content.decode()
        self.assertIn("Técnico a cargo", html)
        self.assertIn("Avance global", html)

    def test_avisos_bajan_desde_el_usuario(self):
        """Los toasts de eventos salen junto al usuario, no abajo."""
        from django.contrib.staticfiles import finders

        with open(finders.find("css/dogger-theme.css"), encoding="utf-8") as f:
            css = f.read()
        pila = css.split(".toast-stack")[1].split("}")[0]
        self.assertIn("top:", pila)
        self.assertNotIn("bottom:", pila)
