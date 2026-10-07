"""El manual de uso se descarga según el rol de la cuenta."""
import os

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import URLResolver, reverse

from apps.accounts import views as cuentas

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _nombres_de_ruta(app):
    """Nombres de url que expone una app del proyecto."""
    from django.urls import get_resolver

    nombres = []

    def recorrer(patrones):
        for patron in patrones:
            if isinstance(patron, URLResolver):
                recorrer(patron.url_patterns)
            elif patron.name:
                nombres.append(patron.name)

    recorrer(get_resolver().url_patterns)
    return nombres


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ManualPorRolTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Usuario = get_user_model()
        cls.cuentas = {rol: Usuario.objects.create_user(
            "%s@dogger.com.co" % rol, rol.capitalize(), "dogger1234", rol=rol,
        ) for rol in ("admin", "tecnico", "usuario", "observador")}

    def descarga(self, rol):
        self.client.force_login(self.cuentas[rol])
        return self.client.get(reverse("accounts:descargar_manual"))

    def test_cada_rol_baja_su_manual(self):
        for rol, esperado in (
            ("admin", "manual-administrador.docx"),
            ("tecnico", "manual-tecnico.docx"),
            ("usuario", "manual-usuario.docx"),
        ):
            respuesta = self.descarga(rol)
            self.assertEqual(respuesta.status_code, 200, rol)
            self.assertEqual(respuesta["Content-Type"], DOCX)
            self.assertIn(esperado, respuesta["Content-Disposition"])
            # Un .docx de verdad: empieza con la firma del formato Office.
            contenido = b"".join(respuesta.streaming_content)
            self.assertTrue(contenido.startswith(b"PK"), rol)

    def test_el_observador_usa_el_manual_del_tecnico(self):
        """Su sesion es de solo lectura sobre las mismas listas y fichas."""
        respuesta = self.descarga("observador")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("manual-tecnico.docx", respuesta["Content-Disposition"])

    def test_sin_sesion_manda_al_acceso(self):
        respuesta = self.client.get(reverse("accounts:descargar_manual"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/login", respuesta.headers["Location"])

    def test_ajustes_muestra_descarga_y_vista_previa(self):
        self.client.force_login(self.cuentas["tecnico"])
        html = self.client.get(reverse("accounts:ajustes")).content.decode()

        self.assertIn(reverse("accounts:descargar_manual"), html)
        self.assertIn("manual-tecnico.docx", html)
        self.assertIn("data-manual-vista-previa", html)
        self.assertIn('id="manualPreview"', html)
        # El manual vive dentro de un marco: no hay un boton aparte que
        # saque al usuario de los ajustes.
        self.assertIn(reverse("accounts:ver_manual"), html)
        self.assertIn('class="manual-preview-frame"', html)
        self.assertNotIn("Abrir manual", html)

    def test_sin_archivo_no_ofrece_la_descarga(self):
        """Si el .docx no esta en el servidor, no se muestra un boton que falla."""
        original = cuentas.archivo_manual
        cuentas.archivo_manual = lambda rol, extension="docx": None
        try:
            self.client.force_login(self.cuentas["usuario"])
            html = self.client.get(reverse("accounts:ajustes")).content.decode()
        finally:
            cuentas.archivo_manual = original

        self.assertNotIn(reverse("accounts:descargar_manual"), html)
        # Sin boton de vista previa ni el marco del manual. El atributo
        # "data-manual-vista-previa" sigue en el script, que solo lo busca.
        self.assertNotIn('<button type="button" class="btn btn-outline btn-sm" data-manual-vista-preva>',
                         html)
        self.assertNotIn('<dialog class="manual-preview"', html)
        # Sin manual no queda ningun enlace al manual.
        self.assertNotIn(reverse("accounts:ver_manual"), html)

    def test_el_manual_se_ve_en_pantalla(self):
        """La vista previa entrega el PDF del rol, en linea y como PDF."""
        self.client.force_login(self.cuentas["usuario"])
        respuesta = self.client.get(reverse("accounts:ver_manual"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertIn("inline", respuesta["Content-Disposition"])
        self.assertIn("manual-usuario.pdf", respuesta["Content-Disposition"])
        self.assertTrue(respuesta.streaming)
        # Y arranca con la firma de un PDF de verdad.
        with open(os.path.join(os.path.dirname(cuentas.__file__),
                               "documentos", "manual-usuario.pdf"), "rb") as archivo:
            esperado = archivo.read(5)
        self.assertEqual(b"".join(respuesta.streaming_content)[:5], esperado)

    def test_el_pdf_tambiene_es_el_del_rol(self):
        self.client.force_login(self.cuentas["tecnico"])
        respuesta = self.client.get(reverse("accounts:ver_manual"))
        self.assertIn("manual-tecnico.pdf", respuesta["Content-Disposition"])

    def test_el_manual_necesita_sesion(self):
        respuesta = self.client.get(reverse("accounts:ver_manual"))
        self.assertEqual(respuesta.status_code, 302)

    def test_el_manual_html_plano_ya_no_existe(self):
        """La version de texto plano se elimino: el manual es el documento."""
        self.assertIn("ver_manual", _nombres_de_ruta(""))
        self.assertNotIn("manual_uso", _nombres_de_ruta(""))
        self.assertFalse(os.path.isfile(os.path.join(
            os.path.dirname(os.path.dirname(cuentas.__file__)),
            "templates", "tickets", "manual_uso.html")))

    def test_los_tres_manuales_estan_en_el_servidor(self):
        carpeta = os.path.join(os.path.dirname(cuentas.__file__), "documentos")
        for base in ("manual-usuario", "manual-tecnico", "manual-administrador"):
            for extension in ("docx", "pdf"):
                ruta = os.path.join(carpeta, base + "." + extension)
                self.assertTrue(os.path.isfile(ruta), ruta)
