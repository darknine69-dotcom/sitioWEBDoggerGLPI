"""Chat corporativo de soporte: hilos, permisos, adjuntos y widget."""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Usuario
from apps.notificaciones.models import Notificacion
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
class ChatWidgetTest(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            email="ana@x.com", password="x", nombre="Ana", rol=Usuario.Rol.USUARIO
        )
        self.tec = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )
        self.admin = Usuario.objects.create_user(
            email="adm@x.com", password="x", nombre="Adm", rol=Usuario.Rol.ADMIN
        )
        self.obs = Usuario.objects.create_user(
            email="obs@x.com", password="x", nombre="Obs", rol=Usuario.Rol.OBSERVADOR
        )
        punto = Punto.objects.create(nombre="Zona Uno")
        ObservadorPunto.objects.create(observador=self.obs, punto=punto)
        self.ticket = Ticket.objects.create(
            titulo="T", descripcion="d", solicitante_nombre="Ana",
            solicitante_email="ana@x.com", solicitante_punto="Zona Uno",
            tecnico_asignado=self.tec,
        )
        self.ajeno = Ticket.objects.create(
            titulo="Otro", descripcion="d", solicitante_nombre="Otro",
            solicitante_email="otro@x.com", solicitante_punto="Zona Ajena",
        )

    def test_anonimo_no_entra(self):
        for nombre, args in (
            ("tickets:chat_tickets", []),
            ("tickets:chat_hilo", [self.ticket.pk]),
        ):
            respuesta = self.client.get(reverse(nombre, args=args) if args else reverse(nombre))
            self.assertEqual(respuesta.status_code, 302)

    def test_usuario_ve_solo_lo_suyo(self):
        self.client.force_login(self.usuario)
        datos = self.client.get(reverse("tickets:chat_tickets")).json()
        self.assertEqual([t["codigo"] for t in datos["tickets"]], [self.ticket.codigo])
        hilo = self.client.get(
            reverse("tickets:chat_hilo", args=[self.ticket.pk])).json()
        self.assertTrue(hilo["ok"])
        self.assertEqual(
            self.client.get(reverse("tickets:chat_hilo", args=[self.ajeno.pk])).status_code,
            403,
        )

    def test_ficha_ans_y_presiones_solo_observador(self):
        TicketComentario.objects.create(ticket=self.ticket, usuario=self.obs, comentario="Revisar", es_presion=True)
        TicketComentario.objects.create(ticket=self.ticket, usuario=self.usuario, comentario="Solicitud", es_presion=True)
        TicketComentario.objects.create(ticket=self.ticket, usuario=self.obs, comentario="Mensaje normal", es_presion=False)
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("tickets:ticket_ficha", args=[self.ticket.pk]))
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()["ticket"]
        self.assertEqual(datos["ans"]["limite_ts"], int(self.ticket.fecha_limite_ans.timestamp()))
        self.assertEqual(len(datos["presiones_observador"]), 1)
        self.assertEqual(datos["presiones_observador"][0]["autor"], "Obs")
        self.assertEqual(datos["presiones_observador"][0]["texto"], "Revisar")
        self.assertEqual(datos["url_detalle"], reverse("tickets:mi_ticket", args=[self.ticket.pk]))
        self.assertEqual(TicketComentario.objects.filter(ticket=self.ticket, es_presion=True).count(), 2)
        self.assertEqual(self.client.get(reverse("tickets:ticket_ficha", args=[self.ajeno.pk])).status_code, 404)

    def test_presion_de_usuario_avisa_solo_al_observador_autorizado(self):
        otro = Usuario.objects.create_user(email="obs-ajeno@x.com", password="x", nombre="Ajeno", rol=Usuario.Rol.OBSERVADOR)
        ObservadorPunto.objects.create(observador=otro, punto=Punto.objects.create(nombre="Zona distinta"))
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("tickets:mi_presionar", args=[self.ticket.pk]), {"mensaje": "Solicito seguimiento"})
        self.assertEqual(respuesta.status_code, 302)
        aviso = Notificacion.objects.get(usuario=self.obs, clave__contains=":presion:")
        self.assertIn(self.ticket.codigo, aviso.titulo)
        self.assertEqual(aviso.url, reverse("tickets:mi_ticket", args=[self.ticket.pk]))
        self.assertFalse(Notificacion.objects.filter(usuario=otro, clave__contains=":presion:").exists())

    def test_presion_desde_ficha_respeta_preferencia_observador(self):
        self.obs.preferencias_notificaciones = {"cambios_ticket": False}
        self.obs.save(update_fields=["preferencias_notificaciones"])
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("tickets:presionar_ticket", args=[self.ticket.pk]), {"mensaje": "Priorizar"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(TicketComentario.objects.filter(ticket=self.ticket, es_presion=True).exists())
        self.assertFalse(Notificacion.objects.filter(usuario=self.obs, clave__contains=":presion:").exists())

    def test_lista_staff_conserva_enlace_y_habilita_ficha(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("tickets:lista"))
        self.assertContains(respuesta, f'data-ticket-ficha="{self.ticket.pk}"')
        self.assertContains(respuesta, reverse("tickets:detalle", args=[self.ticket.pk]))
        datos = self.client.get(reverse("tickets:ticket_ficha", args=[self.ticket.pk])).json()["ticket"]
        self.assertEqual(datos["url_detalle"], reverse("tickets:detalle", args=[self.ticket.pk]))

    def test_responder_avisa_al_otro_lado(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse("tickets:chat_responder", args=[self.ticket.pk]),
            {"mensaje": "Sigo sin imprimir"},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["ok"])
        self.assertTrue(
            TicketComentario.objects.filter(
                ticket=self.ticket, comentario="Sigo sin imprimir").exists())
        self.assertTrue(Notificacion.objects.filter(usuario=self.tec).exists())

    def test_adjuntar_valida_tipo_y_tamano(self):
        self.client.force_login(self.usuario)
        url = reverse("tickets:chat_adjuntar", args=[self.ticket.pk])
        pdf = SimpleUploadedFile("doc.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")
        respuesta = self.client.post(url, {"archivo": pdf})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["ok"])
        exe = SimpleUploadedFile("x.exe", b"bin", content_type="application/x-msdownload")
        self.assertEqual(self.client.post(url, {"archivo": exe}).status_code, 400)
        grande = SimpleUploadedFile("g.pdf", b"x" * (9 * 1024 * 1024),
                                    content_type="application/pdf")
        self.assertEqual(self.client.post(url, {"archivo": grande}).status_code, 400)
        falso = SimpleUploadedFile("falso.png", b"<script>contenido</script>", content_type="image/png")
        self.assertEqual(self.client.post(url, {"archivo": falso}).status_code, 400)
        pdf_falso = SimpleUploadedFile("falso.pdf", b"no es un pdf", content_type="application/pdf")
        self.assertEqual(self.client.post(url, {"archivo": pdf_falso}).status_code, 400)

    def test_adjunto_solo_dueno_y_staff(self):
        from apps.tickets.models import TicketAdjunto

        adj = TicketAdjunto.objects.create(
            ticket=self.ticket, nombre_original="doc.pdf",
            archivo=SimpleUploadedFile("doc.pdf", b"%PDF-1.4",
                                       content_type="application/pdf"),
            mime_type="application/pdf", tamano_bytes=8,
            subido_por="ana@x.com",
        )
        url = reverse("tickets:adjunto", args=[adj.pk])
        self.assertEqual(self.client.get(url).status_code, 302)  # anónimo fuera
        self.client.force_login(self.usuario)  # dueña
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.get("Content-Disposition", ""))
        otro = Usuario.objects.create_user(
            email="otro2@x.com", password="x", nombre="Otro", rol=Usuario.Rol.USUARIO)
        self.client.force_login(otro)  # ajeno
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.tec)  # staff sí
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_observador_solo_su_alcance(self):
        self.client.force_login(self.obs)
        datos = self.client.get(reverse("tickets:chat_tickets")).json()
        self.assertEqual([t["codigo"] for t in datos["tickets"]], [self.ticket.codigo])
        self.assertEqual(
            self.client.get(reverse("tickets:chat_hilo", args=[self.ajeno.pk])).status_code,
            403,
        )
        ElementoMiLista.objects.create(
            observador=self.obs, tipo=ElementoMiLista.TIPO_USUARIO,
            usuario_email="otro@x.com",
        )
        self.assertEqual(
            self.client.get(reverse("tickets:chat_hilo", args=[self.ajeno.pk])).status_code,
            200,
        )

    def test_observador_ve_usuario_asociado_por_clave_foranea(self):
        ElementoMiLista.objects.create(
            observador=self.obs,
            tipo=ElementoMiLista.TIPO_USUARIO,
            usuario=self.usuario,
        )
        ticket_fuera_de_punto = Ticket.objects.create(
            titulo="Cuenta asociada", descripcion="d", solicitante_nombre="Ana",
            solicitante_email=self.usuario.email, solicitante_punto="Zona Ajena",
        )
        self.client.force_login(self.obs)
        tickets = self.client.get(reverse("tickets:chat_tickets")).json()["tickets"]
        self.assertIn(ticket_fuera_de_punto.codigo, [ticket["codigo"] for ticket in tickets])
        self.assertEqual(
            self.client.get(
                reverse("tickets:chat_hilo", args=[ticket_fuera_de_punto.pk])
            ).status_code,
            200,
        )

    def test_tecnico_y_admin_gestionan(self):
        self.client.force_login(self.tec)
        self.assertEqual(
            self.client.get(reverse("tickets:chat_hilo", args=[self.ticket.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("tickets:chat_hilo", args=[self.ajeno.pk])).status_code,
            200,
        )
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("tickets:chat_hilo", args=[self.ticket.pk])).status_code,
            200,
        )

    def test_widget_en_base_para_autenticados(self):
        html = self.client.get(reverse("tickets:portal")).content.decode()
        self.assertNotIn("swFab", html)
        self.client.force_login(self.usuario)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn("swFab", html)
        self.assertIn("Estamos en línea", html)
        self.assertIn("/chat/api/hilo/", html)

    def test_chat_usuarios_solo_staff_y_agrupado(self):
        # El usuario final no entra al desplegable de personas.
        self.client.force_login(self.usuario)
        self.assertEqual(
            self.client.get(reverse("tickets:chat_usuarios")).status_code, 403
        )
        # El staff ve una entrada por solicitante, con su conteo.
        self.client.force_login(self.tec)
        datos = self.client.get(reverse("tickets:chat_usuarios")).json()
        self.assertTrue(datos["ok"])
        por_email = {u["email"]: u for u in datos["usuarios"]}
        self.assertIn("ana@x.com", por_email)
        self.assertIn("otro@x.com", por_email)
        self.assertEqual(por_email["ana@x.com"]["n_tickets"], 1)
        self.assertEqual(por_email["ana@x.com"]["nombre"], "Ana")

    def test_chat_tickets_filtra_por_usuario(self):
        self.client.force_login(self.tec)
        todos = self.client.get(reverse("tickets:chat_tickets")).json()["tickets"]
        self.assertEqual(len(todos), 2)
        unos = self.client.get(
            reverse("tickets:chat_tickets") + "?usuario=ana@x.com").json()["tickets"]
        self.assertEqual([t["codigo"] for t in unos], [self.ticket.codigo])
        # El filtro respeta mayúsculas y ajenos al alcance no aparecen.
        otros = self.client.get(
            reverse("tickets:chat_tickets") + "?usuario=OTRO@x.com").json()["tickets"]
        self.assertEqual([t["codigo"] for t in otros], [self.ajeno.codigo])
        ningunos = self.client.get(
            reverse("tickets:chat_tickets") + "?usuario=nadie@x.com").json()["tickets"]
        self.assertEqual(ningunos, [])

    def test_chat_tickets_dice_el_tecnico_asignado(self):
        """El buscador del chat responde «quién atiende este ticket»: cada
        ticket trae el nombre del técnico y vacío cuando no hay ninguno."""
        self.client.force_login(self.tec)
        por_codigo = {
            t["codigo"]: t
            for t in self.client.get(reverse("tickets:chat_tickets")).json()["tickets"]
        }
        con_tec = por_codigo[self.ticket.codigo]
        self.assertEqual(con_tec["tecnico"], "Tec")
        self.assertEqual(con_tec["tecnico_email"], "tec@x.com")
        sin_tec = por_codigo[self.ajeno.codigo]
        self.assertEqual(sin_tec["tecnico"], "")
        self.assertEqual(sin_tec["tecnico_email"], "")

    def test_buscar_tickets_tecnico_por_codigo_y_tecnico(self):
        """La lupa del botón X busca por código, título, estado o técnico y
        devuelve el enlace al detalle con el técnico asignado."""
        self.client.force_login(self.tec)
        url = reverse("tickets:buscar_tickets_tecnico")

        por_codigo = self.client.get(url, {"q": self.ticket.codigo}).json()
        self.assertTrue(por_codigo["ok"])
        aciertos = {t["codigo"]: t for t in por_codigo["tickets"]}
        self.assertIn(self.ticket.codigo, aciertos)
        self.assertEqual(aciertos[self.ticket.codigo]["tecnico"], "Tec")
        self.assertEqual(aciertos[self.ticket.codigo]["tecnico_rol"], "tecnico")
        self.assertEqual(
            aciertos[self.ticket.codigo]["url"],
            reverse("tickets:detalle", args=[self.ticket.pk]),
        )

        # Buscar por el nombre del técnico también lo encuentra.
        por_tec = self.client.get(url, {"q": "Tec"}).json()["tickets"]
        self.assertIn(self.ticket.codigo, {t["codigo"] for t in por_tec})

        # Menos de dos letras no consulta nada.
        self.assertEqual(self.client.get(url, {"q": "T"}).json()["tickets"], [])

    def test_buscador_global_descripcion_y_aislamiento(self):
        self.ticket.descripcion = "impresora especial bloqueada"
        self.ticket.save(update_fields=["descripcion"])
        self.ajeno.descripcion = "impresora especial ajena"
        self.ajeno.save(update_fields=["descripcion"])
        self.client.force_login(self.usuario)
        url = reverse("tickets:buscar_tickets_tecnico")
        data = self.client.get(url, {"q": "impresora especial", "global": "1"}).json()
        self.assertEqual([t["codigo"] for t in data["tickets"]], [self.ticket.codigo])
        self.assertIn("prioridad_display", data["tickets"][0])
        self.assertIn("ans_vencido", data["tickets"][0])
        self.assertFalse(self.client.get(url, {"q": "Zona Ajena", "global": "1"}).json()["puntos"])
        self.assertEqual(self.client.get(url, {"q": "Zona Uno", "global": "1"}).json()["puntos"][0]["nombre"], "Zona Uno")

    def test_buscador_funciones_por_rol_y_sinonimos(self):
        url = reverse("tickets:buscar_tickets_tecnico")
        for user in (self.admin, self.tec, self.usuario, self.obs):
            self.client.force_login(user)
            def ids(query):
                return {x["id"] for x in self.client.get(url, {"q": query, "global": "1"}).json()["funciones"]}
            self.assertIn("password", ids("contrasena"))
            self.assertIn("notificaciones", ids("notificaciones"))
            if user == self.admin:
                self.assertIn("pagina", ids("dar permiso"))
                self.assertIn("usuarios-admin", ids("cambiar rol"))
            else:
                self.assertNotIn("pagina", ids("permisos"))
                self.assertNotIn("usuarios-admin", ids("crear cuenta"))
        self.client.force_login(self.obs)
        nombres = {x["id"] for x in self.client.get(url, {"q": "monitoreo", "global": "1"}).json()["funciones"]}
        self.assertNotIn("monitoreo-admin", nombres)

    def test_registro_funciones_destinos_existen(self):
        from apps.tickets.search_registry import REGISTRY
        from django.urls import resolve
        for entry in REGISTRY:
            with self.subTest(funcion=entry[0]):
                self.assertIsNotNone(resolve(reverse(entry[5])))

    def test_busqueda_opciones_visualizacion_para_todos_los_roles(self):
        url = reverse("tickets:buscar_tickets_tecnico")
        opciones = {"visualizacion": "preferencias-visualizacion", "accesibilidad": "preferencias-accesibilidad", "color del menú": "preferencias-navegacion", "idioma": "preferencias-general"}
        for usuario in (self.admin, self.tec, self.usuario, self.obs):
            self.client.force_login(usuario)
            for consulta, destino in opciones.items():
                with self.subTest(rol=usuario.rol, consulta=consulta):
                    data = self.client.get(url, {"q": consulta, "global": "1"}).json()
                    self.assertTrue(any(x["url"] == reverse("accounts:perfil") + "#" + destino for x in data["funciones"]))

    def test_visualizacion_no_repite_los_modos(self):
        url = reverse("tickets:buscar_tickets_tecnico")
        for usuario in (self.admin, self.tec, self.usuario, self.obs):
            self.client.force_login(usuario)
            for consulta in ("visualización", "modo claro", "modo oscuro"):
                with self.subTest(rol=usuario.rol, consulta=consulta):
                    data = self.client.get(url, {"q": consulta, "global": "1"}).json()
                    ids = [item["id"] for item in data["funciones"] if item["url"] == reverse("accounts:perfil") + "#preferencias-visualizacion"]
                    self.assertEqual(ids, ["visualizacion"])

    def test_buscador_registros_independientes_y_zonas_privadas(self):
        from apps.tickets.models import Categoria, ZonaObservador
        Categoria.objects.create(nombre="Equipo sin tickets", grupo="Infraestructura", activo=True)
        otro = Usuario.objects.create_user(email="sin-ticket@x.com", password="x", nombre="Cuenta singular", rol=Usuario.Rol.USUARIO)
        ZonaObservador.objects.create(observador=self.obs, nombre="Zona privada única")
        otro_obs = Usuario.objects.create_user(email="otro-obs@x.com", password="x", nombre="Otro observador", rol=Usuario.Rol.OBSERVADOR)
        url = reverse("tickets:buscar_tickets_tecnico")
        self.client.force_login(self.usuario)
        data = self.client.get(url, {"q": "Equipo sin tickets", "global": "1"}).json()
        self.assertIn("Equipo sin tickets", [x["nombre"] for x in data["registros"]])
        data = self.client.get(url, {"q": "Cuenta singular", "global": "1"}).json()
        self.assertNotIn("Cuenta singular", [x["nombre"] for x in data["registros"]])
        self.client.force_login(self.admin)
        data = self.client.get(url, {"q": "Cuenta singular", "global": "1"}).json()
        cuenta = next(x for x in data["registros"] if x["nombre"] == otro.nombre)
        self.assertIn("abrir=" + str(otro.pk), cuenta["url"])
        self.client.force_login(self.obs)
        data = self.client.get(url, {"q": "Zona privada", "global": "1"}).json()
        self.assertIn("Zona privada única", [x["nombre"] for x in data["registros"]])
        self.client.force_login(otro_obs)
        data = self.client.get(url, {"q": "Zona privada", "global": "1"}).json()
        self.assertNotIn("Zona privada única", [x["nombre"] for x in data["registros"]])

    def test_buscador_devuelve_destinos_directos(self):
        from apps.tickets.models import Categoria
        categoria = Categoria.objects.create(nombre="Impresión directa", grupo="Equipos", activo=True)
        self.client.force_login(self.admin)
        url = reverse("tickets:buscar_tickets_tecnico")
        data = self.client.get(url, {"q": "Impresión directa", "global": "1"}).json()
        item = next(x for x in data["registros"] if x["nombre"] == categoria.nombre)
        self.assertEqual(item["url"], reverse("tickets:categorias_arbol") + "#buscar-categoria-" + str(categoria.pk))
        data = self.client.get(url, {"q": "crear usuario", "global": "1"}).json()
        item = next(x for x in data["funciones"] if x["id"] == "crear-cuenta")
        self.assertEqual(item["url"], reverse("tickets:usuarios") + "#buscar-crear-cuenta")
