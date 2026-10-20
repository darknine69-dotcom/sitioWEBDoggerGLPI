"""
Vista de categorías del usuario (Categorías, en el menú lateral).

El usuario llega aquí para saber en qué casillar reportar. Si la página solo
muestra nombres, no sirve de nada: tiene que decir qué cubre cada categoría y
en qué grupo vive, sin obligarlo a abrir modales para enterarse.
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.tickets.management.commands.seed_categorias import CATEGORIAS
from apps.tickets.models import Categoria, CategoriaGrupo
from apps.tickets.sugerencia_categoria import que_cubre, que_cubre_grupo, sugerir_categoria


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

    def test_muestra_el_significado_personalizado_de_la_subcategoria(self):
        categoria = Categoria.objects.get(
            grupo="Soporte TI",
            nombre="Software",
        )
        descripcion_anterior = que_cubre(categoria.grupo, categoria.nombre)
        categoria.descripcion = "Incluye fallas de conexión y acceso a la red local."
        categoria.save(update_fields=["descripcion"])

        respuesta = self.client.get(self.url)

        self.assertContains(
            respuesta,
            "Incluye fallas de conexión y acceso a la red local.",
        )
        self.assertNotContains(respuesta, descripcion_anterior)

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


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class AdministracionCategoriasTest(TestCase):
    def setUp(self):
        administrador = get_user_model().objects.create_user(
            "admin-categorias@dogger.com.co",
            "Administrador",
            "dogger1234",
            rol="admin",
        )
        self.client.force_login(administrador)

    def test_editar_subcategoria_precarga_significado_existente_del_catalogo(self):
        categoria = Categoria.objects.create(
            grupo="Soporte TI",
            nombre="Software",
            prioridad_default="media",
        )
        respuesta = self.client.get(reverse("tickets:categorias_arbol"))
        descripcion_catalogo = que_cubre("Soporte TI", "Software")
        self.assertTrue(descripcion_catalogo)
        self.assertContains(
            respuesta,
            f'<textarea name="descripcion" rows="2" placeholder="Edita qué casos cubre y cuándo elegirla">{descripcion_catalogo}</textarea>',
            html=True,
        )
        self.assertContains(
            respuesta,
            "Modifica el significado actual; si lo dejas vacío",
        )
        categoria.refresh_from_db()
        self.assertEqual(categoria.descripcion, "")

    def test_crea_categoria_principal_y_subcategoria_disponible_en_ticket(self):
        respuesta = self.client.post(
            reverse("tickets:categoria_grupo_crear"),
            {"nombre": "Infraestructura nueva"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(
            CategoriaGrupo.objects.filter(nombre="Infraestructura nueva").exists()
        )

        admin_categorias = self.client.get(reverse("tickets:categorias_arbol"))
        self.assertContains(admin_categorias, "Nueva categoría principal")
        self.assertContains(admin_categorias, "Nueva subcategoría")
        self.assertContains(
            admin_categorias,
            'data-inline-toggle="formCategoriaGrupo"',
        )
        self.assertContains(
            admin_categorias,
            'data-inline-toggle="crear-sub-1"',
        )
        self.assertContains(
            admin_categorias,
            "Nueva subcategoría en Infraestructura nueva",
        )
        self.assertNotContains(admin_categorias, "cat-new-sub-form")
        self.assertEqual(
            admin_categorias.context["form"].fields["grupo"].widget.input_type,
            "select",
        )
        self.assertIn(
            ("Infraestructura nueva", "Infraestructura nueva"),
            admin_categorias.context["form"].fields["grupo"].choices,
        )
        grupo_vacio = next(
            item for item in admin_categorias.context["arbol"]
            if item["grupo"] == "Infraestructura nueva"
        )
        self.assertEqual(grupo_vacio["subcategorias"], [])

        respuesta = self.client.post(
            reverse("tickets:categoria_crear"),
            {
                "grupo": "Infraestructura nueva",
                "nombre": "Red de pruebas",
                "descripcion": "Problemas de conexión de la red en las estaciones.",
                "prioridad_default": "alta",
                "ans_horas": 8,
                "glpi_category_id": "",
                "tecnico_default": "",
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        categoria = Categoria.objects.get(
            grupo="Infraestructura nueva", nombre="Red de pruebas"
        )
        self.assertEqual(
            categoria.descripcion,
            "Problemas de conexión de la red en las estaciones.",
        )

        formulario_ticket = self.client.get(reverse("tickets:crear_ticket"))
        self.assertContains(
            formulario_ticket,
            f'<option value="{categoria.pk}">Red de pruebas</option>',
            html=True,
        )
        sugerencias = json.loads(formulario_ticket.context["cat_sugerencias_json"])
        self.assertTrue(
            any(item.get("id") == categoria.pk for item in sugerencias)
        )
        self.assertEqual(
            sugerir_categoria("Falla la Red de pruebas", ""),
            categoria,
        )
        self.assertEqual(admin_categorias.context["total_grupos"], 1)
        self.assertEqual(admin_categorias.context["total_subcategorias_activas"], 0)

        admin_categorias = self.client.get(reverse("tickets:categorias_arbol"))
        self.assertEqual(admin_categorias.context["total_subcategorias_activas"], 1)
        self.assertContains(
            admin_categorias,
            '<option value="Infraestructura nueva" selected>Infraestructura nueva</option>',
            html=True,
        )
        self.assertContains(
            admin_categorias,
            "Problemas de conexión de la red en las estaciones.",
        )
        self.assertContains(
            admin_categorias,
            '<textarea name="descripcion" rows="2"',
        )
        self.assertContains(
            admin_categorias,
            'textarea name="descripcion" rows="2"',
        )
        self.assertContains(
            admin_categorias,
            "Problemas de conexión de la red en las estaciones.",
        )

        actualizacion = self.client.post(
            reverse("tickets:categoria_actualizar", args=[categoria.pk]),
            {
                "grupo": "Infraestructura nueva",
                "nombre": "Red de pruebas",
                "descripcion": "Conectividad, cableado y acceso a internet.",
                "prioridad_default": "alta",
                "ans_horas": 8,
                "glpi_category_id": "",
                "tecnico_default": "",
            },
        )
        self.assertEqual(actualizacion.status_code, 302)
        categoria.refresh_from_db()
        self.assertEqual(
            categoria.descripcion,
            "Conectividad, cableado y acceso a internet.",
        )

    def test_no_crea_subcategoria_con_categoria_principal_inexistente(self):
        respuesta = self.client.post(
            reverse("tickets:categoria_crear"),
            {
                "grupo": "Grupo que no existe",
                "nombre": "Subcategoría inválida",
                "descripcion": "Descripción de prueba",
                "prioridad_default": "media",
                "ans_horas": 12,
                "glpi_category_id": "",
                "tecnico_default": "",
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(
            Categoria.objects.filter(nombre="Subcategoría inválida").exists()
        )
