"""Monitoreo por zonas: el admin ve y administra lo que creó cada supervisor."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

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
        self.assertEqual(miembro["total"], 1)
        self.assertEqual(len(miembro["tickets"]), 1)
        self.assertEqual(miembro["tickets"][0]["codigo"], Ticket.objects.first().codigo)
        self.assertEqual(miembro["tecnico"], "Tec")
        html = respuesta.content.decode()
        self.assertNotIn("Panel corporativo de supervisores y zonas", html)
        self.assertIn("Supervisor a cargo", html)
        self.assertIn("ana@x.com", html)
        self.assertIn('id="monQuitarBtn"', html)
        self.assertIn("monQuitarSeleccionados", html)
        self.assertIn("pan-cifras", html)
        self.assertIn("data-mon-ticket", html)
        self.assertIn('id="monAlternarZonas"', html)
        self.assertIn('grid.classList.toggle("is-zonas-plegadas", plegadas)', html)
        self.assertIn(
            f'href="{reverse("tickets:monitoreo_zona_detalle", args=[self.zona.pk])}"',
            html,
        )
        self.assertIn('target="_blank" rel="noopener noreferrer"', html)
        self.assertIn(f'id="za-{self.zona.pk}"', html)
        self.assertNotIn('data-mon-card-view=', html)
        dash = respuesta.context["dash"]
        self.assertEqual(dash["supervisores"], 1)
        self.assertEqual(dash["zonas"], 1)
        self.assertEqual(dash["cuentas"], 1)
        self.assertEqual(dash["abiertos"], 1)

    def test_ojito_abre_detalle_de_cuentas_de_zona_en_modo_lectura(self):
        respuesta = self.client.get(
            reverse("tickets:monitoreo_zona_detalle", args=[self.zona.pk])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["admin"])
        self.assertEqual(respuesta.context["resumen"]["cuentas"], 1)
        html = respuesta.content.decode()
        self.assertIn("Cuentas asignadas a esta zona", html)
        self.assertIn("ana@x.com", html)
        self.assertIn(Ticket.objects.first().codigo, html)
        self.assertIn(
            reverse("tickets:monitoreo_cuenta_detalle", args=[self.elemento.pk]),
            html,
        )
        self.assertIn(
            f'href="{reverse("tickets:monitoreo_admin")}#zonas"',
            html,
        )
        self.assertNotIn("Sacar de la zona", html)
        self.assertNotIn("Crear zona", html)

    def test_detalle_admin_no_permite_acceso_a_tecnico_ni_zona_inexistente(self):
        self.client.force_login(self.tec)
        self.assertEqual(
            self.client.get(
                reverse("tickets:monitoreo_zona_detalle", args=[self.zona.pk])
            ).status_code,
            403,
        )
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(
                reverse("tickets:monitoreo_zona_detalle", args=[999999])
            ).status_code,
            404,
        )

    def test_muestra_ans_y_prioridad_en_tarjetas_de_cuenta(self):
        urgente = Ticket.objects.create(
            titulo="Urgente vencido", descripcion="d",
            solicitante_nombre="Ana", solicitante_email="ana@x.com",
            solicitante_punto="Zona Uno", prioridad=Ticket.Prioridad.URGENTE,
        )
        Ticket.objects.filter(pk=urgente.pk).update(
            fecha_creacion=timezone.now() - timedelta(hours=50),
            solicitante_email="Ana@X.com",
        )

        respuesta = self.client.get(reverse("tickets:monitoreo_admin"))
        miembro = respuesta.context["zonas_creadas"][0]["zonas"][0]["miembros"][0]
        self.assertEqual(miembro["ans_vencidos"], 1)
        self.assertEqual(miembro["ans_por_vencer"], 0)
        self.assertEqual(miembro["urgentes"], 1)
        self.assertIn(urgente.pk, {t["pk"] for t in miembro["tickets"]})
        html = respuesta.content.decode()
        self.assertIn("mon-miembro-ans-vencido", html)
        self.assertIn("ANS vencido", html)
        self.assertIn(
            f'href="{reverse("tickets:monitoreo_zona_detalle", args=[self.zona.pk])}"',
            html,
        )

    def test_muestra_accion_presionar_en_lugar_de_quitar_si_ans_esta_por_vencer(self):
        ticket = Ticket.objects.get(solicitante_email="ana@x.com")
        Ticket.objects.filter(pk=ticket.pk).update(
            fecha_creacion=timezone.now() - timedelta(hours=ticket.ans_horas - 1)
        )

        respuesta = self.client.get(reverse("tickets:monitoreo_admin"))
        miembro = respuesta.context["zonas_creadas"][0]["zonas"][0]["miembros"][0]
        self.assertEqual(len(miembro["ans_tickets"]), 1)
        self.assertEqual(miembro["ans_tickets"][0]["pk"], ticket.pk)
        html = respuesta.content.decode()
        self.assertIn("data-mon-presionar", html)
        self.assertIn('id="monPresionarModal"', html)
        self.assertIn("data-estado=\"por-vencer\"", html)

    def test_admin_presiona_al_tecnico_solo_para_ticket_activo_con_ans_alertable(self):
        from apps.notificaciones.models import Notificacion
        from apps.tickets.models import TicketComentario

        ticket = Ticket.objects.get(solicitante_email="ana@x.com")
        Ticket.objects.filter(pk=ticket.pk).update(
            fecha_creacion=timezone.now() - timedelta(hours=ticket.ans_horas - 1)
        )

        respuesta = self.client.post(
            reverse("tickets:monitoreo_presionar", args=[ticket.pk]),
            {"mensaje": "Priorizar por favor"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(
            TicketComentario.objects.filter(
                ticket=ticket,
                usuario=self.admin,
                comentario="Priorizar por favor",
                es_presion=True,
                es_interno=False,
            ).exists()
        )
        self.assertTrue(Notificacion.objects.filter(usuario=self.tec).exists())

        Ticket.objects.filter(pk=ticket.pk).update(estado=Ticket.Estado.RESUELTO)
        respuesta = self.client.post(
            reverse("tickets:monitoreo_presionar", args=[ticket.pk]),
            {"mensaje": "Ya no aplica"},
            follow=True,
        )
        self.assertContains(respuesta, "Solo se puede presionar por tickets activos")
        self.assertFalse(
            TicketComentario.objects.filter(ticket=ticket, comentario="Ya no aplica").exists()
        )

    def test_admin_puede_quitar_cuentas_seleccionadas_sin_borrarlas_de_mi_lista(self):
        respuesta = self.client.post(
            reverse("tickets:monitoreo_zona_miembros_quitar"),
            {
                "zona_id": self.zona.pk,
                "elemento_ids": [self.elemento.pk],
                "volver": reverse("tickets:monitoreo_admin"),
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        self.elemento.refresh_from_db()
        self.assertIsNone(self.elemento.zona_id)
        self.assertTrue(
            ElementoMiLista.objects.filter(
                pk=self.elemento.pk, observador=self.obs
            ).exists()
        )

    def test_quitar_cuenta_de_otra_zona_no_la_mueve(self):
        otra_zona = ZonaObservador.objects.create(
            observador=self.obs, nombre="Sur"
        )
        respuesta = self.client.post(
            reverse("tickets:monitoreo_zona_miembros_quitar"),
            {
                "zona_id": otra_zona.pk,
                "elemento_ids": [self.elemento.pk],
                "volver": reverse("tickets:monitoreo_admin"),
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        self.elemento.refresh_from_db()
        self.assertEqual(self.elemento.zona_id, self.zona.pk)

    def test_admin_puede_cambiar_color_de_la_zona_con_la_paleta(self):
        respuesta = self.client.post(
            reverse("tickets:monitoreo_zona_color", args=[self.zona.pk]),
            {"color": "#1D4ED8", "volver": reverse("tickets:monitoreo_admin")},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.zona.refresh_from_db()
        self.assertEqual(self.zona.color, "#1D4ED8")

        respuesta = self.client.post(
            reverse("tickets:monitoreo_zona_color", args=[self.zona.pk]),
            {"color": "red", "volver": reverse("tickets:monitoreo_admin")},
        )
        self.assertEqual(respuesta.status_code, 404)
        self.zona.refresh_from_db()
        self.assertEqual(self.zona.color, "#1D4ED8")

    def test_sin_zonas_muestra_aviso(self):
        self.zona.delete()
        html = self.client.get(reverse("tickets:monitoreo_admin")).content.decode()
        self.assertIn("Ningún observador ha creado zonas todavía", html)



    def test_buscar_cuentas_por_nombre_o_correo(self):
        url = reverse("tickets:monitoreo_cuentas_buscar")
        datos = self.client.get(url, {"q": "an"}).json()
        correos = [c["email"] for c in datos["cuentas"]]
        self.assertIn("ana@x.com", correos)
        self.assertEqual(
            self.client.get(url, {"q": "a"}).json()["cuentas"], [])
        self.client.force_login(Usuario.objects.create_user(
            email="t2@x.com", password="x", nombre="T2",
            rol=Usuario.Rol.TECNICO))
        self.assertEqual(
            self.client.get(url, {"q": "an"}).status_code, 403)

    def test_filtro_zona_mira_lugares_de_tickets(self):
        url = reverse("tickets:monitoreo_admin")
        ctx = self.client.get(url, {"observador": self.obs.pk}).context
        self.assertIn("Zona Uno", ctx["puntos_ticket"])
        ctx2 = self.client.get(
            url, {"observador": self.obs.pk, "zona": "Zona Uno"}).context
        correos = [f["email"] for f in ctx2["filas"]]
        self.assertIn("ana@x.com", correos)
        ctx3 = self.client.get(
            url, {"observador": self.obs.pk, "zona": "Otro Lado"}).context
        self.assertNotIn("ana@x.com", [f["email"] for f in ctx3["filas"]])

    def test_zona_sigue_visible_si_al_dueno_le_cambian_el_rol(self):
        """La zona se agrupa por quien la creó, no por quien hoy es observador."""
        self.obs.rol = Usuario.Rol.USUARIO
        self.obs.save(update_fields=["rol"])
        respuesta = self.client.get(reverse("tickets:monitoreo_admin"))
        self.assertEqual(respuesta.status_code, 200)
        bloques = respuesta.context["zonas_creadas"]
        self.assertEqual(len(bloques), 1)
        self.assertEqual(bloques[0]["zonas"][0]["zona"].nombre, "Norte")
        html = respuesta.content.decode()
        self.assertIn("Norte", html)
        self.assertIn("rol actual", html)

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
                reverse("tickets:monitoreo_zona_color", args=[self.zona.pk]),
                {"color": "#1D4ED8"},
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
        # La conversación se abre con clic en el ticket, no plana.
        self.assertIn("Tickets y sus conversaciones", html)
        self.assertIn(f'data-miembro-toggle="conv-{ticket.pk}"', html)

    def test_ficha_usuario_es_su_vista_principal(self):
        respuesta = self.client.get(
            reverse("tickets:monitoreo_cuenta_detalle", args=[self.elemento.pk])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["vista_principal"], "Mis solicitudes")
        html = respuesta.content.decode()
        self.assertIn("Vista principal de Ana", html)
        self.assertIn("Sus solicitudes", html)
        # Mismo diseño de su cuenta: hero, KPIs y tabla corp.
        self.assertIn("corp-hero", html)
        self.assertIn("corp-kpis", html)
        self.assertIn("tickets-table", html)

    def test_ficha_tecnico_muestra_lo_que_atiende_y_su_calificacion(self):
        elemento_tec = ElementoMiLista.objects.create(
            observador=self.obs, tipo=ElementoMiLista.TIPO_USUARIO,
            usuario=self.tec, usuario_email="tec@x.com", zona=self.zona,
        )
        respuesta = self.client.get(
            reverse("tickets:monitoreo_cuenta_detalle", args=[elemento_tec.pk])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["vista_principal"], "Panel Técnico")
        self.assertEqual(respuesta.context["asignados_total"], 1)
        self.assertIsNotNone(respuesta.context["calificacion"])
        html = respuesta.content.decode()
        self.assertIn("Lo que atiende", html)
        self.assertIn("Calificación", html)

    def test_filas_del_monitoreo_llevan_a_la_vista_principal(self):
        html = self.client.get(reverse("tickets:monitoreo_admin")).content.decode()
        url_ficha = reverse(
            "tickets:monitoreo_cuenta_detalle", args=[self.elemento.pk]
        )
        self.assertIn(f'data-href="{url_ficha}"', html)
        self.assertIn(f'href="{url_ficha}"', html)

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
        self.assertIn("axFab", html_admin)
        self.assertIn("Accesos rápidos", html_admin)
        self.client.force_login(self.obs)
        html_obs = self.client.get(
            reverse("tickets:obs_zonas")
        ).content.decode()
        self.assertIn("axFab", html_obs)
        self.assertIn("Chat de soporte", html_obs)

    def test_supervisor_renombra_su_zona(self):
        self.client.force_login(self.obs)
        respuesta = self.client.post(
            reverse("tickets:obs_zonas"),
            {"zona_id": self.zona.pk, "nuevo_nombre": "Centro"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.zona.refresh_from_db()
        self.assertEqual(self.zona.nombre, "Centro")


    def test_quitar_zona_saca_de_la_lista(self):
        from apps.tickets.models import ElementoMiLista, MonitoreoAuditoria

        url = reverse("tickets:monitoreo_quitar_zona")
        respuesta = self.client.post(url, {
            "observador": self.obs.pk, "email": "ana@x.com", "zona": "Norte"})
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(ElementoMiLista.objects.filter(
            observador=self.obs, usuario_email="ana@x.com").exists())
        self.assertTrue(MonitoreoAuditoria.objects.filter(
            accion="quitar_miembro", zona_nombre="Norte").exists())

    def test_quitar_saca_de_donde_este(self):
        from apps.tickets.models import ElementoMiLista

        url = reverse("tickets:monitoreo_quitar_zona")
        respuesta = self.client.post(url, {
            "observador": self.obs.pk, "email": "ana@x.com", "zona": "Sur"},
            follow=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(ElementoMiLista.objects.filter(
            observador=self.obs, usuario_email="ana@x.com").exists())
        self.assertContains(respuesta, "fuera de")

    def test_tabla_con_badge_de_zona_y_rol_punto_de_venta(self):
        html = self.client.get(
            reverse("tickets:monitoreo_admin"),
            {"observador": self.obs.pk}).content.decode()
        self.assertIn("zona-badge", html)
        self.assertIn("Norte", html)
        self.assertIn("Punto de venta", html)

    def test_badge_de_zona_de_otro_supervisor_tambien_se_ve(self):
        """La columna Zona muestra la zona de la cuenta aunque sea de otro
        supervisor distinto al elegido en el filtro."""
        from apps.tickets.models import ElementoMiLista, ZonaObservador

        otro = Usuario.objects.create_user(
            email="obs2@x.com", password="x", nombre="Sup2",
            rol=Usuario.Rol.OBSERVADOR,
        )
        beto = Usuario.objects.create_user(
            email="beto@x.com", password="x", nombre="Beto",
            rol=Usuario.Rol.USUARIO,
        )
        zona2 = ZonaObservador.objects.create(observador=otro, nombre="Sin Fin")
        ElementoMiLista.objects.create(
            observador=otro, tipo=ElementoMiLista.TIPO_USUARIO,
            usuario=beto, usuario_email="beto@x.com", zona=zona2,
        )
        html = self.client.get(
            reverse("tickets:monitoreo_admin"),
            {"observador": self.obs.pk}).content.decode()
        self.assertIn("Sin Fin", html)

    def test_agregar_avisa_al_supervisor(self):
        from apps.notificaciones.models import Notificacion

        self.client.post(reverse("tickets:monitoreo_agregar"), {
            "observador": self.obs.pk, "email": "nuevo@x.com", "zona": "Norte"})
        self.assertTrue(Notificacion.objects.filter(
            usuario=self.obs, titulo__icontains="Norte").exists())

    def test_quitar_avisa_al_supervisor(self):
        from apps.notificaciones.models import Notificacion

        self.client.post(reverse("tickets:monitoreo_quitar_zona"), {
            "observador": self.obs.pk, "email": "ana@x.com", "zona": "Norte"})
        self.assertTrue(Notificacion.objects.filter(
            usuario=self.obs, titulo__icontains="salió").exists())

    def test_crear_zona_avisa_al_supervisor(self):
        from apps.notificaciones.models import Notificacion

        self.client.post(reverse("tickets:monitoreo_zona_crear"), {
            "observador": self.obs.pk, "nombre": "Centro"})
        self.assertTrue(Notificacion.objects.filter(
            usuario=self.obs, titulo__icontains="Centro").exists())

    def test_admin_crea_carpeta_para_supervisor(self):
        from apps.tickets.models import ZonaObservador

        url = reverse("tickets:monitoreo_zona_crear")
        respuesta = self.client.post(url, {
            "observador": self.obs.pk, "nombre": "Centro"})
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(ZonaObservador.objects.filter(
            observador=self.obs, nombre="Centro").exists())
        html = self.client.get(
            reverse("tickets:monitoreo_admin"),
            {"observador": self.obs.pk}).content.decode()
        self.assertIn("Centro", html)

    def test_crear_zona_sin_nombre_no_rompe(self):
        from apps.tickets.models import ZonaObservador

        n = ZonaObservador.objects.count()
        respuesta = self.client.post(
            reverse("tickets:monitoreo_zona_crear"),
            {"observador": self.obs.pk, "nombre": "  "})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(ZonaObservador.objects.count(), n)


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
        self.assertIn("resuelto global", html)

    def test_monitoreo_es_tablero_con_graficos_y_tablas(self):
        self._ticket("ana@x.com")
        self.client.post(reverse("tickets:obs_agregar"), {"email": "ana@x.com"})
        respuesta = self.client.get(reverse("tickets:obs_monitoreo"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["top_tecnicos"], [("Tec", 1)])
        self.assertEqual(len(respuesta.context["dona"]), 3)
        html = respuesta.content.decode()
        for texto in (
            "Zonas a cargo", "Carga por zona", "Técnicos que atienden",
            "Resumen por zona", "Estado de tu lista", "obs-dona-svg",
            "Análisis de tickets", "Solicitudes por categoría",
        ):
            self.assertIn(texto, html)
        self.assertLess(
            html.index("Análisis de tickets"),
            html.index('<section id="por-vencer"'),
        )
        self.assertLess(html.index("Solicitudes por categoría"), html.index("Estado de tu lista"))

    def test_zonas_a_cargo_bajan_a_las_zonas(self):
        from apps.tickets.models import ZonaObservador

        self._ticket("ana@x.com")
        self.client.post(reverse("tickets:obs_agregar"), {"email": "ana@x.com"})
        zona = ZonaObservador.objects.create(observador=self.obs, nombre="Norte")
        elemento = ElementoMiLista.objects.get(observador=self.obs)
        elemento.zona = zona
        elemento.save()
        respuesta = self.client.get(reverse("tickets:obs_monitoreo"))
        html = respuesta.content.decode()
        self.assertIn("Zonas a cargo", html)
        self.assertIn('href="#zonas-monitoreo"', html)
        self.assertIn('id="zonas-monitoreo"', html)
        self.assertNotIn("modalZonas", html)
        # La cuenta principal lleva a su ficha.
        self.assertIn("/observador/usuarios/?q=ana%40x.com", html)

    def test_sin_zona_se_muestra_como_grupo_para_que_cuadre_el_total(self):
        """Lo que no está en ninguna carpeta sale en su propio grupo.

        Si no aparecía en ninguna parte, el indicador de Cuentas —que suma
        toda la lista— decía una más de las que se veían en las tarjetas y
        en el Resumen por zona.
        """
        Usuario.objects.create_user(
            email="ana@x.com", password="x", nombre="Ana",
            rol=Usuario.Rol.USUARIO, ubicacion="Zona Uno",
        )
        self._ticket("ana@x.com")
        self.client.post(reverse("tickets:obs_agregar"), {"email": "ana@x.com"})
        respuesta = self.client.get(reverse("tickets:obs_monitoreo"))
        grupos = respuesta.context["grupos"]
        self.assertEqual(len(grupos), 1)
        self.assertIsNone(grupos[0]["zona"])
        self.assertEqual(grupos[0]["filas"][0]["email"], "ana@x.com")
        html = respuesta.content.decode()
        self.assertIn("<strong>Sin zona</strong>", html)
        # La suma del Resumen por zona cuadra con el indicador de Cuentas.
        self.assertEqual(
            sum(len(g["filas"]) for g in grupos), respuesta.context["total"]
        )
        todos = respuesta.context["todos_usuarios"]
        ana = [u for u in todos if u["email"] == "ana@x.com"]
        self.assertEqual(len(ana), 1)
        self.assertTrue(ana[0]["en_lista"])
        self.assertIn("Actividad reciente", html)
        self.assertNotIn("Todos los usuarios", html)

    def test_miembro_muestra_datos_reales_aunque_sean_de_otro_punto(self):
        from apps.tickets.models import ZonaObservador

        Usuario.objects.create_user(
            email="ana@x.com", password="x", nombre="Ana",
            rol=Usuario.Rol.USUARIO, ubicacion="Zona Uno",
        )
        ticket = self._ticket("ana@x.com", punto="Zona Ajena")
        self.client.post(reverse("tickets:obs_agregar"), {"email": "ana@x.com"})
        zona = ZonaObservador.objects.create(observador=self.obs, nombre="Azul")
        elemento = ElementoMiLista.objects.get(observador=self.obs)
        elemento.zona = zona
        elemento.save()
        respuesta = self.client.get(reverse("tickets:obs_monitoreo"))
        filas = respuesta.context["filas"]
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["total"], 1)
        self.assertEqual(filas[0]["abiertos"], 1)
        self.assertEqual(filas[0]["tecnico"], "Tec")
        html = respuesta.content.decode()
        self.assertIn(ticket.codigo, html)
        self.assertIn("data-zona-toggle", html)
        self.assertIn("data-miembro-toggle", html)
        self.assertIn("obs-crate", html)
        self.assertIn("obs-crate-global", html)
        self.assertIn("Tickets recientes", html)
        self.assertNotIn("Últimas respuestas", html)
        self.assertIn("Presionar al técnico", html)
        self.assertIn("obs-leyenda-item", html)
        self.assertIn("Todo resuelto, sin pendientes", html)
        self.assertIn("Exportar datos", html)
        self.assertNotIn("Imprimir", html)
        self.assertIn("act-ticket st-abierto", html)
        self.assertIn("detalles ›", html)
        self.assertIn("Presionar al técnico", html)
        self.assertIn("act-nudge", html)
        self.assertIn('id="actBuscar"', html)
        self.assertIn('id="actLista"', html)

    def test_avisos_bajan_desde_el_usuario(self):
        """Los toasts de eventos salen junto al usuario, no abajo."""
        from django.contrib.staticfiles import finders

        with open(finders.find("css/dogger-theme.css"), encoding="utf-8") as f:
            css = f.read()
        pila = css.split(".toast-stack")[1].split("}")[0]
        self.assertIn("top:", pila)
        self.assertNotIn("bottom:", pila)

    def test_respuestas_de_admin_no_salen_en_ultimas(self):
        from apps.tickets.models import TicketComentario, ZonaObservador

        admin = Usuario.objects.create_user(
            email="admin@x.com", password="x", nombre="Blandon",
            rol=Usuario.Rol.ADMIN,
        )
        ticket = self._ticket("ana@x.com")
        TicketComentario.objects.create(
            ticket=ticket, usuario=admin, comentario="Pronto recibirá atención"
        )
        TicketComentario.objects.create(
            ticket=ticket, usuario=self.tec, comentario="Ya voy en camino"
        )
        self.client.post(reverse("tickets:obs_agregar"), {"email": "ana@x.com"})
        zona = ZonaObservador.objects.create(observador=self.obs, nombre="Norte")
        elemento = ElementoMiLista.objects.get(observador=self.obs)
        elemento.zona = zona
        elemento.save()
        html = self.client.get(reverse("tickets:obs_monitoreo")).content.decode()
        self.assertIn("Ya voy en camino", html)
        self.assertNotIn("Pronto recibirá atención", html)
        self.assertIn("obs-resp-lista", html)

    def test_respuestas_muestran_tres_y_resto_con_scroll(self):
        from apps.tickets.models import TicketComentario, ZonaObservador

        ticket = self._ticket("ana@x.com")
        for i in range(5):
            TicketComentario.objects.create(
                ticket=ticket, usuario=self.tec, comentario=f"Avance {i}"
            )
        self.client.post(reverse("tickets:obs_agregar"), {"email": "ana@x.com"})
        zona = ZonaObservador.objects.create(observador=self.obs, nombre="Norte")
        elemento = ElementoMiLista.objects.get(observador=self.obs)
        elemento.zona = zona
        elemento.save()
        html = self.client.get(reverse("tickets:obs_monitoreo")).content.decode()
        for i in range(5):
            self.assertIn(f"Avance {i}", html)
        self.assertIn("obs-resp-lista", html)

    def test_detalles_abre_la_ficha_del_ticket_en_lectura(self):
        ticket = self._ticket("ana@x.com")
        self.client.post(reverse("tickets:obs_agregar"), {"email": "ana@x.com"})
        respuesta = self.client.get(reverse("tickets:mi_ticket", args=[ticket.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["solo_lectura"])
        html = respuesta.content.decode()
        self.assertIn(ticket.codigo, html)
        self.assertNotIn("mi_responder", html)
        self.assertNotIn("Editar ticket", html)

    def test_presionar_tecnico_envia_mensaje_y_avisa(self):
        from apps.tickets.models import TicketComentario
        from apps.notificaciones.models import Notificacion

        ticket = self._ticket("ana@x.com")
        self.client.post(reverse("tickets:obs_agregar"), {"email": "ana@x.com"})
        respuesta = self.client.post(
            reverse("tickets:obs_presionar", args=[ticket.pk]),
            {"mensaje": "Por favor resolver rápido",
             "volver": reverse("tickets:obs_monitoreo")},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(
            TicketComentario.objects.filter(
                ticket=ticket, comentario="Por favor resolver rápido",
                usuario=self.obs, es_interno=False,
            ).exists()
        )
        self.assertTrue(
            Notificacion.objects.filter(usuario=self.tec).exists()
        )

    def test_presionar_fuera_de_alcance_da_404(self):
        ticket = self._ticket("otro@x.com", punto="Zona Ajena")
        respuesta = self.client.post(
            reverse("tickets:obs_presionar", args=[ticket.pk]),
            {"mensaje": "Hola"},
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_presionar_sin_mensaje_avisa(self):
        ticket = self._ticket("ana@x.com")
        self.client.post(reverse("tickets:obs_agregar"), {"email": "ana@x.com"})
        respuesta = self.client.post(
            reverse("tickets:obs_presionar", args=[ticket.pk]),
            {"mensaje": "  ", "volver": reverse("tickets:obs_monitoreo")},
            follow=True,
        )
        self.assertContains(respuesta, "Escribe el mensaje")

    def test_ficha_fuera_de_alcance_da_404(self):
        ticket = self._ticket("otro@x.com", punto="Zona Ajena")
        respuesta = self.client.get(reverse("tickets:mi_ticket", args=[ticket.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_observador_se_une_a_la_conversacion(self):
        from apps.tickets.models import TicketComentario

        ticket = self._ticket("ana@x.com")
        self.client.post(reverse("tickets:obs_agregar"), {"email": "ana@x.com"})
        respuesta = self.client.post(
            reverse("tickets:mi_responder_obs", args=[ticket.pk]),
            {"comentario": "Quedo atento al avance"},
        )
        self.assertEqual(respuesta.status_code, 302)
        comentario = TicketComentario.objects.get(
            ticket=ticket, comentario="Quedo atento al avance"
        )
        self.assertEqual(comentario.usuario, self.obs)
        self.assertFalse(comentario.es_interno)
        html = self.client.get(
            reverse("tickets:mi_ticket", args=[ticket.pk])
        ).content.decode()
        self.assertIn("chat-msg-observador", html)
        self.assertIn("Quedo atento al avance", html)

    def test_chat_muestra_badge_de_tecnico_y_observador(self):
        from apps.tickets.models import TicketComentario

        ticket = self._ticket("ana@x.com")
        TicketComentario.objects.create(
            ticket=ticket, usuario=self.tec, comentario="Ya voy en camino"
        )
        self.client.post(reverse("tickets:obs_agregar"), {"email": "ana@x.com"})
        self.client.post(
            reverse("tickets:mi_responder_obs", args=[ticket.pk]),
            {"comentario": "Quedo atento"},
        )
        html = self.client.get(
            reverse("tickets:mi_ticket", args=[ticket.pk])
        ).content.decode()
        self.assertIn("chat-badge-observador", html)
        self.assertIn("Observador", html)
        self.assertIn("chat-badge-soporte", html)
        self.assertIn("Técnico", html)

    def test_observador_no_responde_fuera_de_alcance(self):
        ticket = self._ticket("otro@x.com", punto="Zona Ajena")
        respuesta = self.client.post(
            reverse("tickets:mi_responder_obs", args=[ticket.pk]),
            {"comentario": "Hola"},
        )
        self.assertEqual(respuesta.status_code, 404)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class PanelSupervisorTest(TestCase):
    """Mi lista trae el panel de dos columnas, con sus zonas y sus puntos a
    la izquierda y los usuarios de lo que se elija a la derecha. Monitoreo y
    Usuarios se quedan con lo suyo, sin ese panel."""

    def setUp(self):
        self.obs = Usuario.objects.create_user(
            email="obs@x.com", password="x", nombre="Sup",
            rol=Usuario.Rol.OBSERVADOR,
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
        self.zona = ZonaObservador.objects.create(observador=self.obs, nombre="Norte")
        self.client.force_login(self.obs)

    def _ticket(self, email="ana@x.com", punto="Zona Uno"):
        return Ticket.objects.create(
            titulo="T", descripcion="d", solicitante_nombre="Ana",
            solicitante_email=email, solicitante_punto=punto,
            estado=Ticket.Estado.ABIERTO, tecnico_asignado=self.tec,
        )

    def _agregar(self, email="ana@x.com", zona=None):
        self.client.post(reverse("tickets:obs_agregar"), {"email": email})
        if zona is not None:
            elemento = ElementoMiLista.objects.get(
                observador=self.obs, usuario_email=email
            )
            elemento.zona = zona
            elemento.save()

    def test_el_panel_esta_solo_en_mi_lista(self):
        html = self.client.get(reverse("tickets:obs_mi_lista")).content.decode()
        # El panel ya no lleva título, solo la tarjeta del supervisor.
        self.assertNotIn("Panel corporativo de zonas y puntos", html)
        self.assertIn("Supervisor a cargo", html)
        self.assertIn('class="pan-grid"', html)
        self.assertIn("Buscar usuario", html)
        self.assertIn("Cerrar", html)

        # Monitoreo y Usuarios no lo traen: cada uno sigue con lo suyo.
        for nombre_vista in ("obs_monitoreo", "obs_usuarios"):
            with self.subTest(vista=nombre_vista):
                respuesta = self.client.get(reverse(f"tickets:{nombre_vista}"))
                self.assertEqual(respuesta.status_code, 200)
                html = respuesta.content.decode()
                self.assertNotIn('class="pan-grid"', html)
                self.assertNotIn("Panel corporativo de zonas y puntos", html)
                self.assertNotIn("Supervisor a cargo", html)
                self.assertNotIn('id="panRight"', html)

    def test_la_cuenta_de_mi_lista_sale_en_su_zona(self):
        self._ticket()
        self._agregar(zona=self.zona)
        respuesta = self.client.get(reverse("tickets:obs_mi_lista"))
        panel = respuesta.context["panel"]
        self.assertEqual([z["nombre"] for z in panel["zonas"]], ["Norte"])
        self.assertEqual(panel["zonas"][0]["cuentas"], 1)
        self.assertEqual(panel["zonas"][0]["abiertos"], 1)
        self.assertEqual(panel["zonas"][0]["estado"], "amarillo")
        self.assertIn("ana@x.com", panel["zonas"][0]["usuarios"][0]["email"])
        html = respuesta.content.decode()
        self.assertIn('data-pan-nombre="Norte"', html)

    def test_el_punto_asignado_ya_no_se_pinta_en_mi_lista(self):
        """Mi lista ya no pinta «Mis puntos» ni «Sin zona»: solo zonas."""
        self._ticket()
        self._agregar()
        html = self.client.get(reverse("tickets:obs_mi_lista")).content.decode()
        self.assertIn("Mis zonas", html)
        self.assertIn('data-pan-nombre="Norte"', html)
        self.assertNotIn("Mis puntos", html)
        self.assertNotIn("Sin zona", html)
        self.assertNotIn('data-pan-nombre="Zona Uno"', html)

    def test_una_zona_sin_cuentas_sigue_visible(self):
        panel = self.client.get(
            reverse("tickets:obs_mi_lista")
        ).context["panel"]
        self.assertEqual(panel["zonas"][0]["nombre"], "Norte")
        self.assertEqual(panel["zonas"][0]["cuentas"], 0)
        self.assertEqual(panel["zonas"][0]["estado"], "verde")

    def test_los_datos_van_en_json_para_el_buscador_de_la_derecha(self):
        self._ticket()
        self._agregar(zona=self.zona)
        html = self.client.get(reverse("tickets:obs_mi_lista")).content.decode()
        self.assertIn('id="pan-datos"', html)
        self.assertIn("ana@x.com", html)

@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class PanelSupervisorDosPanelesTest(TestCase):
    """El mismo visor de dos columnas que el admin, pero en Mi lista y solo
    con lo del supervisor: zonas y puntos a la izquierda, sus usuarios a la
    derecha. Monitoreo y Usuarios se quedan sin él."""

    def setUp(self):
        self.obs = Usuario.objects.create_user(
            email="obs@x.com", password="x", nombre="Sup", rol=Usuario.Rol.OBSERVADOR
        )
        self.tec = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )
        self.ana = Usuario.objects.create_user(
            email="ana@x.com", password="x", nombre="Ana",
            rol=Usuario.Rol.USUARIO, ubicacion="Zona Uno",
        )
        self.beto = Usuario.objects.create_user(
            email="beto@x.com", password="x", nombre="Beto",
            rol=Usuario.Rol.USUARIO, ubicacion="Zona Uno",
        )
        punto = Punto.objects.create(nombre="Zona Uno")
        ObservadorPunto.objects.create(observador=self.obs, punto=punto)
        self.zona = ZonaObservador.objects.create(observador=self.obs, nombre="Norte")
        self.client.force_login(self.obs)

        # Ana sí está en la lista y en la zona; Beto solo tiene tickets.
        self._ticket(self.ana)
        self.client.post(reverse("tickets:obs_agregar"), {"email": "ana@x.com"})
        elemento = ElementoMiLista.objects.get(observador=self.obs)
        elemento.zona = self.zona
        elemento.save()
        self._ticket(self.beto)

    def _ticket(self, usuario):
        return Ticket.objects.create(
            titulo="T", descripcion="d",
            solicitante_nombre=usuario.nombre, solicitante_email=usuario.email,
            solicitante_punto=usuario.ubicacion,
            estado=Ticket.Estado.ABIERTO, tecnico_asignado=self.tec,
        )

    def test_solo_mi_lista_trae_el_panel_de_dos_columnas(self):
        respuesta = self.client.get(reverse("tickets:obs_mi_lista"))
        self.assertEqual(respuesta.status_code, 200)
        panel = respuesta.context["panel"]
        self.assertEqual([z["nombre"] for z in panel["zonas"]], ["Norte"])
        # El panel ya no agrupa por punto: solo zonas.
        self.assertNotIn("puntos", panel)
        self.assertNotIn("sin_zona", panel)
        self.assertEqual(panel["zonas"][0]["cuentas"], 1)
        self.assertEqual(panel["supervisor"]["nombre"], "Sup")
        html = respuesta.content.decode()
        self.assertIn('class="pan-grid"', html)
        self.assertNotIn("Panel corporativo de zonas y puntos", html)
        self.assertIn("Supervisor a cargo", html)
        self.assertIn("Mis zonas", html)
        self.assertNotIn("Mis puntos", html)
        self.assertIn('data-pan-nombre="Norte"', html)
        self.assertNotIn('data-pan-nombre="Zona Uno"', html)
        self.assertIn("Buscar usuario", html)
        self.assertIn('id="panRight"', html)

        # Ni Monitoreo ni Usuarios lo traen.
        for vista in ("obs_monitoreo", "obs_usuarios"):
            with self.subTest(vista=vista):
                otro = self.client.get(reverse("tickets:" + vista))
                self.assertEqual(otro.status_code, 200)
                self.assertNotIn('class="pan-grid"', otro.content.decode())

    def test_el_panel_de_la_derecha_trae_a_sus_usuarios_en_json(self):
        html = self.client.get(reverse("tickets:obs_mi_lista")).content.decode()
        self.assertIn('id="pan-datos"', html)
        self.assertIn("ana@x.com", html)
        self.assertIn("Supervisor a cargo", html)

    def test_el_panel_no_quita_nada_de_lo_que_ya_habia(self):
        html = self.client.get(reverse("tickets:obs_monitoreo")).content.decode()
        # El tablero de siempre sigue completo, sin el panel encima.
        self.assertIn("Zonas a cargo", html)
        self.assertIn("resuelto global", html)
        self.assertNotIn('class="pan-grid"', html)
        # Y el texto largo de ayuda de las zonas, intacto.
        self.assertIn("Cada supervisor a cargo con sus zonas", html)

    def test_en_usuarios_sigue_la_tabla_de_todos(self):
        html = self.client.get(reverse("tickets:obs_usuarios")).content.decode()
        self.assertNotIn('class="pan-grid"', html)
        self.assertIn("Todos los usuarios", html)
        self.assertIn("beto@x.com", html)
