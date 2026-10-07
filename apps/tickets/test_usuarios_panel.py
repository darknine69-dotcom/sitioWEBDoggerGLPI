"""Panel de Accesos (usuarios): contadores vivos y tabla con datos reales."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Usuario


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class AccesosPanelTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="admin@x.com", password="x", nombre="Admin",
            rol=Usuario.Rol.ADMIN,
        )
        self.client.force_login(self.admin)
        # El force_login toca el last_login: se fija viejo para no contar.
        Usuario.objects.filter(pk=self.admin.pk).update(
            last_login=timezone.now() - timedelta(hours=5),
            ultima_actividad=None,
        )
        self.admin.refresh_from_db()

    def _persona(self, email, nombre="Persona", rol=Usuario.Rol.USUARIO):
        return Usuario.objects.create_user(
            email=email, password="x", nombre=nombre, rol=rol
        )

    def _marcar(self, usuario, login=None, actividad=None, creado=None):
        campos = {}
        if login is not None:
            campos["last_login"] = login
        if actividad is not None:
            campos["ultima_actividad"] = actividad
        if creado is not None:
            campos["fecha_creacion"] = creado
        if campos:
            Usuario.objects.filter(pk=usuario.pk).update(**campos)
            usuario.refresh_from_db()
        return usuario

    def _pagina(self):
        respuesta = self.client.get(reverse("tickets:usuarios"))
        self.assertEqual(respuesta.status_code, 200)
        return respuesta

    def test_en_linea_cuenta_latido_y_login(self):
        ahora = timezone.now()
        a = self._marcar(
            self._persona("a@x.com"), login=ahora - timedelta(hours=1),
            actividad=ahora,
        )
        b = self._marcar(self._persona("b@x.com"), login=ahora)
        self._marcar(
            self._persona("c@x.com"), login=ahora - timedelta(hours=2),
            actividad=ahora - timedelta(hours=2),
        )
        self.assertEqual(self._pagina().context["n_en_linea"], 2)
        self.assertTrue(a.pk and b.pk)

    def test_nuevos_esta_semana(self):
        ahora = timezone.now()
        self._persona("nueva@x.com")
        self._marcar(
            self._persona("vieja@x.com"), creado=ahora - timedelta(days=30)
        )
        # La recién creada más el admin que mira la página.
        self.assertEqual(self._pagina().context["n_nuevos"], 2)

    def test_ultimo_acceso_en_fecha_y_hora(self):
        acceso = timezone.now() - timedelta(hours=2)
        u = self._marcar(self._persona("u@x.com"), login=acceso)
        esperada = timezone.localtime(acceso).strftime("%d/%m/%Y %H:%M")
        html = self._pagina().content.decode()
        self.assertIn(esperada, html)
        self.assertNotIn("hace 2 h", html)
        fila = html.split(f"ue-access-{u.pk}")[1].split("</span>")[0]
        self.assertIn(esperada, fila)

    def test_punto_verde_al_principio_del_nombre(self):
        ahora = timezone.now()
        u = self._marcar(
            self._persona("v@x.com", nombre="Verde Total"),
            login=ahora, actividad=ahora,
        )
        html = self._pagina().content.decode()
        pos_punto = html.find(f'id="ue-dot-{u.pk}"')
        pos_nombre = html.find("<strong>Verde Total</strong>")
        self.assertTrue(0 <= pos_punto < pos_nombre)

    def test_sin_numero_y_estado_en_verde(self):
        self._persona("sintel@x.com", nombre="Sin Tel")
        con = self._persona("contel@x.com", nombre="Con Tel")
        Usuario.objects.filter(pk=con.pk).update(telefono="310 123 4567")
        html = self._pagina().content.decode()
        self.assertIn("Sin número", html)
        self.assertIn("310 123 4567", html)
        self.assertIn('ue-estado ok">Activa', html)
        inactive = self._persona("off@x.com", nombre="Apagada")
        Usuario.objects.filter(pk=inactive.pk).update(activo=False)
        html = self._pagina().content.decode()
        self.assertIn('ue-estado no">Inactiva', html)

    def test_boton_glpi_cuadradito(self):
        html = self.client.get(
            reverse("tickets:usuarios"), {"rol": "tecnico"}
        ).content.decode()
        self.assertIn("mini-btn sq ok", html)

    def test_ficha_ajax_trae_datos_frescos(self):
        ahora = timezone.now()
        u = self._marcar(
            self._persona("f@x.com", nombre="Ficha Fresca"),
            login=ahora - timedelta(days=5), actividad=ahora,
        )
        esperada = timezone.localtime(ahora).strftime("%d/%m/%Y %H:%M")
        rancia = timezone.localtime(ahora - timedelta(days=5)).strftime("%d/%m/%Y")
        html = self.client.get(
            reverse("tickets:usuario_ficha", args=[u.pk])
        ).json()["html"]
        self.assertIn(esperada, html)
        self.assertNotIn(rancia, html)
        self.assertIn("Ficha Fresca", html)

    def test_js_muestra_fecha_absoluta(self):
        from pathlib import Path

        from django.conf import settings

        js = (
            Path(settings.BASE_DIR)
            / "templates/tickets/usuarios.html"
        ).read_text(encoding="utf-8")
        self.assertIn("getHours", js)
        self.assertNotIn("hace ' + Math.floor(min", js)
