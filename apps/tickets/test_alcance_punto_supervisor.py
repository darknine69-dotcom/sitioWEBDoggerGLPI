import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.tickets.models import ElementoMiLista, ObservadorPunto, Punto, Ticket, ZonaObservador


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class AlcancePuntoSupervisorTest(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.punto = users.create_user("punto@example.com", "Punto", "clave", rol="usuario")
        self.otro = users.create_user("otro@example.com", "Otro", "clave", rol="usuario")
        self.ajeno = users.create_user("ajeno@example.com", "Ajeno", "clave", rol="usuario")
        self.supervisor = users.create_user("supervisor@example.com", "Supervisor", "clave", rol="observador")
        self.ajeno_supervisor = users.create_user("ajeno-supervisor@example.com", "Otro supervisor", "clave", rol="observador")
        self.zona = ZonaObservador.objects.create(observador=self.supervisor, nombre="Zona uno")
        self.otra_zona = ZonaObservador.objects.create(observador=self.supervisor, nombre="Zona dos")
        self.zona_ajena = ZonaObservador.objects.create(observador=self.ajeno_supervisor, nombre="Ajena")
        for owner, punto, titulo in [(self.punto, "Propio", "Caso propio"), (self.otro, "Otro punto", "Asunto privado de otro"), (self.ajeno, "Ajeno", "Asunto privado ajeno")]:
            Ticket.objects.create(titulo=titulo, descripcion="Detalle", solicitante_nombre=owner.nombre, solicitante_email=owner.email, solicitante_punto=punto)
        ElementoMiLista.objects.create(observador=self.supervisor, usuario=self.otro, usuario_email=self.otro.email, zona=self.otra_zona)
        ElementoMiLista.objects.create(observador=self.ajeno_supervisor, usuario=self.ajeno, usuario_email=self.ajeno.email, zona=self.zona_ajena)
        self.client.force_login(self.punto)

    def _pivot(self):
        response = self.client.get(reverse("tickets:mi_panel"))
        self.assertEqual(response.status_code, 200)
        return json.loads(response.context["dash_json"])["pivot"]["dimensiones"]

    def test_sin_asignacion_no_ve_datos_generales_ajenos(self):
        dimensiones = self._pivot()
        self.assertEqual(dimensiones["punto"]["rows"], [])
        self.assertTrue(all(not dimension["rows"] for dimension in dimensiones.values()))
        response = self.client.get(reverse("tickets:mi_panel"))
        self.assertEqual(response.context["zona_datos"], {})
        self.assertEqual(response.context["punto_dashboard"]["total"], 1)

    def test_en_lista_sin_carpeta_no_autoriza_datos_generales(self):
        ElementoMiLista.objects.create(observador=self.supervisor, usuario=self.punto, usuario_email=self.punto.email)
        self.assertEqual(self._pivot()["punto"]["rows"], [])

    def test_con_carpeta_ve_agregados_de_la_lista_sin_detalles_ajenos(self):
        ElementoMiLista.objects.create(observador=self.supervisor, usuario=self.punto, usuario_email=self.punto.email, zona=self.zona)
        punto_fisico = Punto.objects.create(nombre="Propio")
        ObservadorPunto.objects.create(observador=self.ajeno_supervisor, punto=punto_fisico)
        Ticket.objects.create(titulo="Mismo punto fuera de lista", descripcion="Detalle", solicitante_nombre="Ajeno", solicitante_email=self.ajeno.email, solicitante_punto="Propio")
        dimensiones = self._pivot()
        labels = {row["label"] for row in dimensiones["punto"]["rows"]}
        self.assertEqual(labels, {"Propio", "Otro punto"})
        self.assertEqual(next(row["total"] for row in dimensiones["punto"]["rows"] if row["label"] == "Propio"), 1)
        for dimension in dimensiones.values():
            for row in dimension["rows"]:
                self.assertEqual(row["tickets"], [])
        response = self.client.get(reverse("tickets:mi_panel"))
        self.assertNotIn("Asunto privado de otro", response.context["dash_json"])
        self.assertNotIn("Asunto privado ajeno", response.context["dash_json"])
        self.assertNotIn(self.ajeno_supervisor.email, [supervisor["correo"] for supervisor in response.context["mi_zona"]["equipo"]])
