"""Zonas propias del observador: crearlas, agrupar gente y seguirla."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

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
class ZonasObservadorTest(TestCase):
    def setUp(self):
        self.obs = Usuario.objects.create_user(
            email="obs@x.com", password="x", nombre="Obs", rol=Usuario.Rol.OBSERVADOR
        )
        self.otro = Usuario.objects.create_user(
            email="otro@x.com", password="x", nombre="Otro", rol=Usuario.Rol.OBSERVADOR
        )
        self.tec = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )
        self.zona_uno = Punto.objects.create(nombre="Zona Uno")
        ObservadorPunto.objects.create(observador=self.obs, punto=self.zona_uno)
        self.client.force_login(self.obs)

    def _ticket(self, nombre, email, punto="Zona Uno",
                estado=Ticket.Estado.ABIERTO):
        return Ticket.objects.create(
            titulo="T",
            descripcion="d",
            solicitante_nombre=nombre,
            solicitante_email=email,
            solicitante_punto=punto,
            estado=estado,
            tecnico_asignado=self.tec,
        )

    def _agregar(self, correo):
        return self.client.post(
            reverse("tickets:obs_agregar"),
            {"email": correo, "volver": reverse("tickets:obs_mi_lista")},
        )

    def _zona(self, nombre="Sede norte"):
        return ZonaObservador.objects.create(observador=self.obs, nombre=nombre)

    # --- crear ---
    def test_crear_zona(self):
        respuesta = self.client.post(
            reverse("tickets:obs_zonas"), {"nombre": "Sede norte"}
        )
        zona = ZonaObservador.objects.get(observador=self.obs)
        self.assertEqual(zona.nombre, "Sede norte")
        self.assertRedirects(
            respuesta, reverse("tickets:obs_zona_detalle", args=[zona.pk])
        )
        html = self.client.get(reverse("tickets:obs_zonas")).content.decode()
        self.assertIn("Sede norte", html)

    def test_crear_zona_exige_nombre(self):
        respuesta = self.client.post(reverse("tickets:obs_zonas"), {"nombre": "  "})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Ponle un nombre", respuesta.content.decode())
        self.assertFalse(ZonaObservador.objects.exists())

    def test_crear_zona_no_duplica_nombre(self):
        self._zona("Sede norte")
        respuesta = self.client.post(
            reverse("tickets:obs_zonas"), {"nombre": "sede NORTE"}
        )
        self.assertIn("Ya tienes una zona", respuesta.content.decode())
        self.assertEqual(
            ZonaObservador.objects.filter(observador=self.obs).count(), 1
        )

    def test_otro_observador_puede_repetir_el_nombre(self):
        self._zona("Sede norte")
        self.client.force_login(self.otro)
        self.client.post(reverse("tickets:obs_zonas"), {"nombre": "Sede norte"})
        self.assertEqual(
            ZonaObservador.objects.filter(observador=self.otro).count(), 1
        )

    # --- agrupar ---
    def test_asignar_y_sacar_miembro(self):
        self._agregar("ana@x.com")
        elemento = ElementoMiLista.objects.get(observador=self.obs)
        zona = self._zona()
        self.client.post(
            reverse("tickets:obs_zona_miembro"),
            {"elemento": elemento.pk, "zona": zona.pk,
             "volver": reverse("tickets:obs_zonas")},
        )
        elemento.refresh_from_db()
        self.assertEqual(elemento.zona, zona)
        html = self.client.get(
            reverse("tickets:obs_zona_detalle", args=[zona.pk])
        ).content.decode()
        self.assertIn("ana@x.com", html)
        self.client.post(
            reverse("tickets:obs_zona_miembro"),
            {"elemento": elemento.pk, "zona": "",
             "volver": reverse("tickets:obs_zona_detalle", args=[zona.pk])},
        )
        elemento.refresh_from_db()
        self.assertIsNone(elemento.zona)

    def test_eliminar_zona_deja_la_gente_sin_zona(self):
        self._agregar("ana@x.com")
        elemento = ElementoMiLista.objects.get(observador=self.obs)
        zona = self._zona()
        elemento.zona = zona
        elemento.save()
        self.client.post(reverse("tickets:obs_zona_eliminar", args=[zona.pk]))
        self.assertFalse(ZonaObservador.objects.exists())
        elemento.refresh_from_db()
        self.assertIsNone(elemento.zona)
        self.assertTrue(ElementoMiLista.objects.filter(pk=elemento.pk).exists())

    # --- seguimiento ---
    def test_detalle_muestra_tickets_y_respuestas(self):
        self._ticket("Ana Ruiz", "ana@x.com")
        self._ticket("Ana Ruiz", "ana@x.com", estado=Ticket.Estado.CERRADO)
        self._agregar("ana@x.com")
        elemento = ElementoMiLista.objects.get(observador=self.obs)
        zona = self._zona()
        elemento.zona = zona
        elemento.save()
        ticket = Ticket.objects.get(solicitante_email="ana@x.com",
                                    estado=Ticket.Estado.ABIERTO)
        TicketComentario.objects.create(
            ticket=ticket, usuario=self.tec, autor_nombre="Tec",
            comentario="Ya voy en camino", es_interno=False,
        )
        TicketComentario.objects.create(
            ticket=ticket, usuario=self.tec, autor_nombre="Tec",
            comentario="Nota interna secreta", es_interno=True,
        )
        html = self.client.get(
            reverse("tickets:obs_zona_detalle", args=[zona.pk])
        ).content.decode()
        self.assertIn("ana@x.com", html)
        self.assertIn("Ya voy en camino", html)
        self.assertNotIn("Nota interna secreta", html)
        self.assertIn("Respuestas de los técnicos", html)

    def test_detalle_no_muestra_zona_ajena_ni_sus_tickets(self):
        self._ticket("Ana Ruiz", "ana@x.com")
        self._agregar("ana@x.com")
        elemento = ElementoMiLista.objects.get(observador=self.obs)
        zona = self._zona()
        elemento.zona = zona
        elemento.save()
        self.client.force_login(self.otro)
        for url in (
            reverse("tickets:obs_zona_detalle", args=[zona.pk]),
            reverse("tickets:obs_zona_eliminar", args=[zona.pk]),
        ):
            with self.subTest(url=url):
                metodo = self.client.get if "eliminar" not in url else self.client.post
                self.assertEqual(metodo(url).status_code, 404)
        respuesta = self.client.post(
            reverse("tickets:obs_zona_miembro"),
            {"elemento": elemento.pk, "zona": ""},
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_sin_rol_de_observador_no_entra(self):
        admin = get_user_model().objects.create_user(
            email="admin@x.com", password="x", nombre="A",
            rol=get_user_model().Rol.ADMIN,
        )
        self.client.force_login(admin)
        self.assertEqual(
            self.client.get(reverse("tickets:obs_zonas")).status_code, 403
        )
