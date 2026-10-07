"""
Vista de categorías del usuario (Categorías, en el menú lateral).

El usuario llega aquí para saber en qué casillar reportar. Si la página solo
muestra nombres, no sirve de nada: tiene que decir qué cubre cada categoría y
en qué grupo vive, sin obligarlo a abrir modales para enterarse.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.tickets.management.commands.seed_categorias import CATEGORIAS
from apps.tickets.models import Categoria
from apps.tickets.sugerencia_categoria import que_cubre, que_cubre_grupo


# Las vistas usan {% static %}: sin este override los tests piden el manifiesto
# de collectstatic, que no existe al correr la suite.
@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class VistaCategoriasUsuario(TestCase):
    @classmethod
    def setUpTestData(cls):
        for grupo, nombre, prioridad in CATEGORIAS:
            Categoria.objects.create(grupo=grupo, nombre=nombre, prioridad_default=prioridad, activo=True)
        cls.user = get_user_model().objects.create_user(
            "lector@dogger.com.co", "Lector", "dogger1234", rol="usuario",
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("tickets:categorias_publico")

    def test_lista_todas_las_categorias(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        for grupo, nombre, _ in CATEGORIAS:
            self.assertContains(respuesta, nombre)

    def test_explica_que_cubre_cada_categoria(self):
        """Cada categoría muestra su línea de "qué cubre" sin que haya que abrirla."""
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.context["total_categorias"], len(CATEGORIAS))
        self.assertEqual(respuesta.context["total_grupos"], len({g for g, _, _ in CATEGORIAS}))
        for grupo, nombre, _ in CATEGORIAS:
            self.assertContains(respuesta, que_cubre(grupo, nombre))

    def test_explica_tambien_los_grupos(self):
        respuesta = self.client.get(self.url)
        for grupo in {g for g, _, _ in CATEGORIAS}:
            self.assertContains(respuesta, que_cubre_grupo(grupo))

    def test_no_usa_modales(self):
        """El detalle se despliega en la misma línea: el usuario no tiene que
        abrir ventanas para saber qué es cada categoría."""
        respuesta = self.client.get(self.url)
        self.assertNotContains(respuesta, "modal-overlay")
        self.assertNotContains(respuesta, "catDetalle")

    def test_crear_solicitud_preselecciona_la_categoria(self):
        """El botón "Crear solicitud aquí" llega con la categoría ya elegida."""
        categoria = Categoria.objects.get(grupo="Puntos de venta", nombre="POS Hardware")
        respuesta = self.client.get(reverse("tickets:crear_ticket"), {"categoria": categoria.pk})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["form"].initial.get("categoria"), categoria.pk)

    def test_categoria_inactiva_o_inventada_no_preselecciona(self):
        inactiva = Categoria.objects.get(grupo="Puntos de venta", nombre="POS Hardware")
        inactiva.activo = False
        inactiva.save(update_fields=["activo"])
        respuesta = self.client.get(reverse("tickets:crear_ticket"), {"categoria": inactiva.pk})
        self.assertNotIn("categoria", respuesta.context["form"].initial)
