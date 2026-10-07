"""Prueba el módulo del Observador.

Se fija sobre todo el caso que se rompió: al agregar una persona a la lista
personal se guardaba sin usuario y sin correo, así que el observador perdía
de vista a quién había agregado y la fila terminaba contando todos los
tickets de sus zonas.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Usuario
from apps.tickets.models import ElementoMiLista, ObservadorPunto, Punto, Ticket


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ObservadorListaTest(TestCase):
    def setUp(self):
        self.observador = Usuario.objects.create_user(
            email="obs@x.com", password="x", nombre="Obs", rol=Usuario.Rol.OBSERVADOR
        )
        self.otro = Usuario.objects.create_user(
            email="otro@x.com", password="x", nombre="Otro", rol=Usuario.Rol.OBSERVADOR
        )
        self.zona = Punto.objects.create(nombre="Zona Uno")
        self.ajena = Punto.objects.create(nombre="Zona Ajena")
        ObservadorPunto.objects.create(observador=self.observador, punto=self.zona)
        self.client.force_login(self.observador)

    def _ticket(self, nombre, punto, email="", estado=Ticket.Estado.ABIERTO,
                prioridad=Ticket.Prioridad.MEDIA):
        return Ticket.objects.create(
            titulo="T",
            descripcion="d",
            prioridad=prioridad,
            estado=estado,
            solicitante_nombre=nombre,
            solicitante_email=email or None,
            solicitante_punto=punto,
        )

    def _agregar(self, correo):
        return self.client.post(
            reverse("tickets:obs_agregar"),
            {"email": correo, "volver": reverse("tickets:obs_mi_lista")},
        )

    # --- el bug: la persona se perdia al agregarla ---
    def test_agregar_persona_sin_usuario_guarda_el_correo(self):
        self._agregar("afectado@x.com")
        fila = ElementoMiLista.objects.get(observador=self.observador)
        self.assertEqual(fila.usuario_email, "afectado@x.com")
        self.assertEqual(fila.tipo, ElementoMiLista.TIPO_USUARIO)

    def test_agregar_persona_con_usuario_lo_enlaza(self):
        registrado = Usuario.objects.create_user(
            email="conuser@x.com", password="x", nombre="Con User",
            rol=Usuario.Rol.USUARIO,
        )
        self._agregar("conuser@x.com")
        fila = ElementoMiLista.objects.get(observador=self.observador)
        self.assertEqual(fila.usuario_email, "conuser@x.com")
        self.assertEqual(fila.usuario_id, registrado.pk)

    def test_agregar_dos_veces_no_duplica(self):
        self._agregar("afectado@x.com")
        self._agregar("afectado@x.com")
        self.assertEqual(
            ElementoMiLista.objects.filter(observador=self.observador).count(), 1
        )

    def test_mi_lista_no_falla_con_persona_sin_usuario(self):
        """Antes esto reventaba con AttributeError al leer usuario_email."""
        self._agregar("afectado@x.com")
        for url in ("tickets:obs_mi_lista", "tickets:obs_monitoreo", "tickets:obs_usuarios"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(reverse(url)).status_code, 200)

    def test_mi_lista_solo_cuenta_los_tickets_de_esa_persona(self):
        self._ticket("Afectado", "Zona Uno", email="afectado@x.com")
        self._ticket("Afectado", "Zona Uno", email="afectado@x.com")
        self._ticket("Otra", "Zona Uno", email="otra@x.com")
        self._agregar("afectado@x.com")
        respuesta = self.client.get(reverse("tickets:obs_mi_lista"))
        self.assertEqual(respuesta.context["filas"][0]["total"], 2)
        self.assertEqual(respuesta.context["filas"][0]["nombre"], "afectado@x.com")

    def test_exportar_no_falla_con_persona_sin_usuario(self):
        self._agregar("afectado@x.com")
        self.assertEqual(self.client.get(reverse("tickets:obs_exportar")).status_code, 200)

    # --- aislamiento por zona ---
    def test_no_ve_personas_de_zonas_ajenas(self):
        self._ticket("De Mi Zona", "Zona Uno", email="mio@x.com")
        self._ticket("De Zona Ajena", "Zona Ajena", email="ajeno@x.com")
        respuesta = self.client.get(reverse("tickets:obs_usuarios"))
        self.assertContains(respuesta, "mio@x.com")
        self.assertNotContains(respuesta, "ajeno@x.com")

    def test_mi_lista_no_arrastra_tickets_de_zona_ajena(self):
        self._ticket("Afectado", "Zona Uno", email="afectado@x.com")
        self._ticket("Afectado", "Zona Ajena", email="afectado@x.com")
        self._agregar("afectado@x.com")
        respuesta = self.client.get(reverse("tickets:obs_mi_lista"))
        self.assertEqual(respuesta.context["filas"][0]["total"], 1)

    def test_otro_observador_no_roba_elementos(self):
        self._agregar("afectado@x.com")
        self.client.force_login(self.otro)
        respuesta = self.client.get(reverse("tickets:obs_mi_lista"))
        self.assertEqual(respuesta.context["filas"], [])

    # --- filtros de la vista de usuarios ---
    def test_filtro_por_texto(self):
        self._ticket("Ana Ruiz", "Zona Uno", email="ana@x.com")
        self._ticket("Beto Diaz", "Zona Uno", email="beto@x.com")
        respuesta = self.client.get(reverse("tickets:obs_usuarios"), {"q": "ana"})
        self.assertContains(respuesta, "ana@x.com")
        self.assertNotContains(respuesta, "beto@x.com")

    def test_filtro_por_zona(self):
        ObservadorPunto.objects.create(observador=self.observador, punto=self.ajena)
        self._ticket("Ana", "Zona Uno", email="ana@x.com")
        self._ticket("Beto", "Zona Ajena", email="beto@x.com")
        respuesta = self.client.get(
            reverse("tickets:obs_usuarios"), {"punto": "Zona Ajena"}
        )
        self.assertContains(respuesta, "beto@x.com")
        self.assertNotContains(respuesta, "ana@x.com")

    def test_filtro_activos_exige_ticket_abierto(self):
        self._ticket("Ana", "Zona Uno", email="ana@x.com")
        self._ticket("Beto", "Zona Uno", email="beto@x.com",
                     estado=Ticket.Estado.CERRADO)
        respuesta = self.client.get(reverse("tickets:obs_usuarios"), {"estado": "activos"})
        self.assertContains(respuesta, "ana@x.com")
        self.assertNotContains(respuesta, "beto@x.com")

    def test_filtro_alerta_exige_urgente_y_abierto(self):
        self._ticket("Ana", "Zona Uno", email="ana@x.com",
                     prioridad=Ticket.Prioridad.URGENTE)
        self._ticket("Beto", "Zona Uno", email="beto@x.com",
                     estado=Ticket.Estado.CERRADO,
                     prioridad=Ticket.Prioridad.URGENTE)
        respuesta = self.client.get(reverse("tickets:obs_usuarios"), {"estado": "alerta"})
        self.assertContains(respuesta, "ana@x.com")
        self.assertNotContains(respuesta, "beto@x.com")

    def test_orden_por_nombre(self):
        self._ticket("Zulma", "Zona Uno", email="zulma@x.com")
        self._ticket("Ana", "Zona Uno", email="ana@x.com")
        respuesta = self.client.get(reverse("tickets:obs_usuarios"), {"orden": "nombre"})
        nombres = [f["nombre"] for f in respuesta.context["filas"]]
        self.assertEqual(nombres, ["Ana", "Zulma"])

    def test_orden_por_abiertos(self):
        self._ticket("Ana", "Zona Uno", email="ana@x.com")
        self._ticket("Beto", "Zona Uno", email="beto@x.com")
        self._ticket("Beto", "Zona Uno", email="beto@x.com")
        respuesta = self.client.get(reverse("tickets:obs_usuarios"), {"orden": "abiertos"})
        nombres = [f["nombre"] for f in respuesta.context["filas"]]
        self.assertEqual(nombres, ["Beto", "Ana"])

    def test_usuarios_muestra_el_total_sin_filtro(self):
        self._ticket("Ana", "Zona Uno", email="ana@x.com")
        self._ticket("Beto", "Zona Uno", email="beto@x.com")
        respuesta = self.client.get(reverse("tickets:obs_usuarios"), {"q": "ana"})
        self.assertEqual(respuesta.context["total"], 1)
        self.assertEqual(respuesta.context["total_sin_filtro"], 2)

    def test_panel_es_tablero_con_indicadores_propios(self):
        import re

        self._ticket("Ana", "Zona Uno", email="ana@x.com")
        self._agregar("ana@x.com")
        respuesta = self.client.get(reverse("tickets:obs_panel"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["total_personas"], 1)
        self.assertEqual(respuesta.context["total_tickets"], 1)
        self.assertEqual(respuesta.context["abiertos"], 1)
        self.assertEqual(respuesta.context["mi_lista_total"], 1)
        clases = set(re.findall(r"dash-hov-[a-z]+", respuesta.content.decode()))
        self.assertEqual(
            clases,
            {
                "dash-hov-usuarios", "dash-hov-total", "dash-hov-abiertos",
                "dash-hov-vencidos", "dash-hov-zonas", "dash-hov-progreso",
            },
        )

    def test_panel_sin_duplicados_y_con_buscador(self):
        html = self.client.get(reverse("tickets:obs_panel")).content.decode()
        self.assertNotIn("obs_usuarios", html)
        self.assertNotIn("Imprimir", html)
        self.assertNotIn("Exportar", html)
        self.assertIn("Buscar y agregar", html)
        self.assertIn("fabObs", html)

    def test_buscador_del_panel_agrega_a_la_lista(self):
        Usuario.objects.create_user(
            email="nueva@x.com", password="x", nombre="Nueva",
            rol=Usuario.Rol.USUARIO,
        )
        respuesta = self.client.get(
            reverse("tickets:obs_panel"), {"q_busc": "nueva"}
        )
        self.assertContains(respuesta, "nueva@x.com")
        self.client.post(
            reverse("tickets:obs_agregar"), {"email": "nueva@x.com"}
        )
        self.assertTrue(
            ElementoMiLista.objects.filter(
                observador=self.observador, usuario_email="nueva@x.com"
            ).exists()
        )

    def test_cuenta_creada_se_ve_aunque_no_tenga_tickets(self):
        Usuario.objects.create_user(
            email="nueva@x.com", password="x", nombre="Nueva",
            rol=Usuario.Rol.USUARIO, ubicacion="Zona Uno",
        )
        respuesta = self.client.get(reverse("tickets:obs_panel"))
        filas = respuesta.context["personas"]
        nueva = [f for f in filas if f["email"] == "nueva@x.com"]
        self.assertEqual(len(nueva), 1)
        self.assertEqual(nueva[0]["total"], 0)
        self.assertIn("sin tickets aún", respuesta.content.decode())

    def test_panel_muestra_el_tecnico_de_cada_cuenta(self):
        tec = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec",
            rol=Usuario.Rol.TECNICO,
        )
        Ticket.objects.create(
            titulo="T", descripcion="d", solicitante_nombre="Ana",
            solicitante_email="ana@x.com", solicitante_punto="Zona Uno",
            tecnico_asignado=tec,
        )
        respuesta = self.client.get(reverse("tickets:obs_panel"))
        ana = [
            f for f in respuesta.context["personas"] if f["email"] == "ana@x.com"
        ]
        self.assertEqual(ana[0]["tecnico"], "Tec")
        self.assertIn("Tec", respuesta.content.decode())

    def test_panel_es_el_monitoreo_por_zonas(self):
        from apps.tickets.models import ZonaObservador

        ticket = self._ticket("Ana", "Zona Uno", email="ana@x.com")
        self._agregar("ana@x.com")
        zona = ZonaObservador.objects.create(observador=self.observador, nombre="Norte")
        elemento = ElementoMiLista.objects.get(observador=self.observador)
        elemento.zona = zona
        elemento.save()
        respuesta = self.client.get(reverse("tickets:obs_panel"))
        self.assertEqual(len(respuesta.context["grupos"]), 1)
        html = respuesta.content.decode()
        self.assertIn("Monitoreo por zonas", html)
        self.assertIn("Norte", html)
        self.assertIn("Técnico a cargo", html)
        self.assertIn(ticket.codigo, html)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ObservadorPermisosTest(TestCase):
    def test_otro_rol_no_entra(self):
        usuario = Usuario.objects.create_user(
            email="admin@x.com", password="x", nombre="A", rol=Usuario.Rol.ADMIN
        )
        self.client.force_login(usuario)
        for nombre in ("obs_panel", "obs_usuarios", "obs_buscar", "obs_mi_lista", "obs_monitoreo"):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.client.get(reverse("tickets:" + nombre)).status_code, 403)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ObservadorBuscadorTest(TestCase):
    def setUp(self):
        self.observador = Usuario.objects.create_user(
            email="obs@x.com", password="x", nombre="Obs", rol=Usuario.Rol.OBSERVADOR
        )
        ObservadorPunto.objects.create(
            observador=self.observador, punto=Punto.objects.create(nombre="Zona Uno")
        )
        self.client.force_login(self.observador)

    def _ticket(self, nombre, punto, email=""):
        return Ticket.objects.create(
            titulo="T", descripcion="d",
            prioridad=Ticket.Prioridad.MEDIA,
            estado=Ticket.Estado.ABIERTO,
            solicitante_nombre=nombre,
            solicitante_email=email or None,
            solicitante_punto=punto,
        )

    def test_busca_por_nombre(self):
        self._ticket("Ana Ruiz", "Zona Uno", email="ana@x.com")
        respuesta = self.client.get(reverse("tickets:obs_buscar"), {"q": "ana"})
        self.assertContains(respuesta, "ana@x.com")

    def test_no_busca_fuera_de_sus_zonas(self):
        self._ticket("Ajena", "Zona Ajena", email="ajena@x.com")
        respuesta = self.client.get(reverse("tickets:obs_buscar"), {"q": "ajena"})
        self.assertNotContains(respuesta, "ajena@x.com")

    def test_filtro_tipo_punto(self):
        self._ticket("Ana", "Zona Uno", email="ana@x.com")
        respuesta = self.client.get(
            reverse("tickets:obs_buscar"), {"q": "Zona", "tipo": "punto"}
        )
        personas = respuesta.context["resultados"]["personas"]
        puntos = respuesta.context["resultados"]["puntos"]
        self.assertEqual(personas, [])
        self.assertEqual([p["nombre"] for p in puntos], ["Zona Uno"])

    def test_filtro_tipo_persona(self):
        self._ticket("Ana", "Zona Uno", email="ana@x.com")
        respuesta = self.client.get(
            reverse("tickets:obs_buscar"), {"q": "Ana", "tipo": "persona"}
        )
        self.assertEqual(
            [p["nombre"] for p in respuesta.context["resultados"]["personas"]], ["Ana"]
        )
        self.assertEqual(respuesta.context["resultados"]["puntos"], [])

    def test_marca_que_ya_esta_en_la_lista(self):
        self._ticket("Ana", "Zona Uno", email="ana@x.com")
        self.client.post(
            reverse("tickets:obs_agregar"),
            {"email": "ana@x.com", "volver": reverse("tickets:obs_buscar")},
        )
        respuesta = self.client.get(reverse("tickets:obs_buscar"), {"q": "ana"})
        self.assertTrue(respuesta.context["resultados"]["personas"][0]["ya_agregado"])
