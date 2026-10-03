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
