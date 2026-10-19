"""Prueba el casillero «Cambiar de rol» y el botón que abre.

El administrador enciende una casilla en la ficha de una cuenta y de ahí en
adelante esa persona ve un botón junto a su nombre, en la barra superior de
cualquier vista, con el que pasa al rol que elija. Dos cosas se cuidan aquí:

  · que nadie se encienda la casilla a sí mismo: solo sale desde la ficha del
    panel, y la vista del cambio la vuelve a mirar antes de tocar nada;
  · que el sistema no se quede sin administrador: la misma guarda que impide
    borrar al último administrador activo también impide que se saque el rol.
"""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Usuario


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class BotonCambiarRolTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="admin@x.com", password="x", nombre="Admin",
            rol=Usuario.Rol.ADMIN,
        )
        self.persona = Usuario.objects.create_user(
            email="lucia@x.com", password="x", nombre="Lucía",
            rol=Usuario.Rol.TECNICO,
        )
        self.client.force_login(self.persona)

    def _encender(self, usuario=None, guardista=None):
        """El administrador enciende la casilla, como lo haría desde la ficha.

        `guardista` deja usar otra cuenta administradora cuando la de prueba
        se cambió de rol para contar administradores.
        """
        u = usuario or self.persona
        self.client.force_login(guardista or self.admin)
        self.client.post(reverse("tickets:usuario_guardar"), {
            "pk": u.pk,
            "nombre": u.nombre,
            "email": u.email,
            "rol": u.rol,
            "activo": "on",
            "cambio_rol_habilitado": "on",
        })
        self.client.force_login(self.persona)

    # ----------------------------------------------------------- el botón
    def test_sin_la_casilla_no_sale_el_boton(self):
        for url in (reverse("accounts:perfil"), reverse("accounts:ajustes")):
            html = self.client.get(url).content.decode()
            self.assertNotIn('id="rolModal"', html)
            self.assertNotIn("rol-cambio-btn", html)

    def test_con_la_casilla_sale_el_boton_en_cualquier_vista(self):
        """El botón vive en la barra superior, así que sale en todas las vistas."""
        self._encender()
        for url in (
            reverse("accounts:perfil"),
            reverse("accounts:ajustes"),
            reverse("tickets:panel_tecnico"),
        ):
            html = self.client.get(url).content.decode()
            self.assertIn("rol-cambio-btn", html, f"No salió el botón en {url}")
            self.assertIn('id="rolModal"', html)

    def test_el_boton_va_junto_al_nombre_del_usuario(self):
        """Está en la barra superior, a la derecha de la tarjeta del usuario."""
        self._encender()
        html = self.client.get(reverse("accounts:perfil")).content.decode()
        self.assertLess(
            html.index('class="user-chip"'),
            html.index("rol-cambio-btn"),
        )

    def test_la_ventana_ofrece_los_cuatro_roles(self):
        self._encender()
        html = self.client.get(reverse("accounts:perfil")).content.decode()
        for rol in ("admin", "tecnico", "usuario", "observador"):
            self.assertIn(f'value="{rol}"', html)
        # El que tiene se marca como actual; las cuatro piden elegir.
        self.assertIn("Tu rol actual", html)
        self.assertEqual(html.count('type="radio" name="rol"'), 4)
        self.assertRegex(html, r'value="tecnico" required\s+checked')

    # ------------------------------------------------------ quién decide
    def test_sin_la_casilla_el_post_no_cambia_nada(self):
        """Aunque llegue el formulario, la casilla manda: no se cambia nada."""
        respuesta = self.client.post(
            reverse("accounts:cambiar_rol"), {"rol": Usuario.Rol.ADMIN}
        )
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.rol, Usuario.Rol.TECNICO)
        self.assertEqual(respuesta.status_code, 302)
        self.assertContains(
            self.client.get(reverse("accounts:perfil")),
            "no tiene habilitado cambiar de rol",
        )

    def test_la_casilla_no_se_puede_encender_desde_los_ajustes(self):
        """La vista del cambio no acepta nada que encienda la casilla."""
        self.client.post(reverse("accounts:ajustes"), {
            "cambio_rol_habilitado": "on",
        })
        self.persona.refresh_from_db()
        self.assertFalse(self.persona.cambio_rol_habilitado)

    def test_el_admin_enciende_la_casilla_desde_la_ficha(self):
        self._encender()
        self.persona.refresh_from_db()
        self.assertTrue(self.persona.cambio_rol_habilitado)

    def test_la_ficha_muestra_la_casilla_marcada(self):
        """El modal «Datos de la cuenta» refleja lo guardado: la fila de la
        tabla manda el valor y el casillero sale donde el administrador lo
        dejó, sin tener que adivinarlo."""
        self._encender()
        self.client.force_login(self.admin)
        html = self.client.get(reverse("tickets:usuarios")).content.decode()
        self.assertIn('name="cambio_rol_habilitado"', html)
        self.assertIn('id="u-cambio-rol"', html)
        self.assertIn('data-fill-cambio-rol="1"', html)
        # Antes de encenderla, otra cuenta muestra la casilla apagada.
        Usuario.objects.create_user(
            email="otra@x.com", password="x", nombre="Otra",
            rol=Usuario.Rol.USUARIO,
        )
        html = self.client.get(reverse("tickets:usuarios")).content.decode()
        self.assertIn('data-fill-cambio-rol="0"', html)

    def test_al_guardar_sin_la_casilla_se_apaga(self):
        """Desmarcarla en la ficha la apaga de verdad."""
        self._encender()
        self.client.force_login(self.admin)
        self.client.post(reverse("tickets:usuario_guardar"), {
            "pk": self.persona.pk, "nombre": self.persona.nombre,
            "email": self.persona.email, "rol": self.persona.rol,
            "activo": "on",
        })
        self.persona.refresh_from_db()
        self.assertFalse(self.persona.cambio_rol_habilitado)

    # --------------------------------------------------------- el cambio
    def test_el_cambio_guarda_el_rol_y_manda_al_panel_nuevo(self):
        self._encender()
        respuesta = self.client.post(
            reverse("accounts:cambiar_rol"), {"rol": Usuario.Rol.USUARIO}
        )
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.rol, Usuario.Rol.USUARIO)
        self.assertEqual(respuesta["Location"], reverse("tickets:mi_panel"))

    def test_el_rol_nuevo_se_ve_en_la_barra(self):
        self._encender()
        self.client.post(
            reverse("accounts:cambiar_rol"), {"rol": Usuario.Rol.OBSERVADOR}
        )
        html = self.client.get(reverse("accounts:perfil")).content.decode()
        self.assertIn("Observador", html)

    def test_cerrar_y_volver_a_entrar_lleva_al_panel_del_rol_nuevo(self):
        self._encender()
        self.client.post(
            reverse("accounts:cambiar_rol"), {"rol": Usuario.Rol.OBSERVADOR}
        )
        self.client.logout()
        self.client.login(email="lucia@x.com", password="x")
        # La portada manda a cada cuenta al panel de su rol.
        self.assertEqual(
            self.client.get(reverse("tickets:portal"))["Location"],
            reverse("tickets:obs_monitoreo"),
        )

    def test_un_rol_inexistente_no_se_aplica(self):
        self._encender()
        self.client.post(reverse("accounts:cambiar_rol"), {"rol": "superman"})
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.rol, Usuario.Rol.TECNICO)

    def test_el_mismo_rol_no_hace_nada_raro(self):
        self._encender()
        respuesta = self.client.post(
            reverse("accounts:cambiar_rol"), {"rol": Usuario.Rol.TECNICO}
        )
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.rol, Usuario.Rol.TECNICO)
        self.assertEqual(respuesta["Location"], reverse("tickets:panel_tecnico"))

    def test_no_toca_a_otra_cuenta_aunque_llegue_su_pk(self):
        """La vista solo mira a quien pidió el cambio; no hay forma de apuntar
        a otra persona desde este formulario."""
        otro = Usuario.objects.create_user(
            email="otro@x.com", password="x", nombre="Otro",
            rol=Usuario.Rol.OBSERVADOR,
        )
        self._encender()
        self.client.post(reverse("accounts:cambiar_rol"), {
            "rol": Usuario.Rol.USUARIO, "pk": otro.pk,
        })
        otro.refresh_from_db()
        self.assertEqual(otro.rol, Usuario.Rol.OBSERVADOR)

    def test_is_staff_sigue_al_rol(self):
        self._encender()
        self.client.post(
            reverse("accounts:cambiar_rol"), {"rol": Usuario.Rol.USUARIO}
        )
        self.persona.refresh_from_db()
        self.assertFalse(self.persona.is_staff)
        self.client.post(
            reverse("accounts:cambiar_rol"), {"rol": Usuario.Rol.ADMIN}
        )
        self.persona.refresh_from_db()
        self.assertTrue(self.persona.is_staff)

    # ------------------------------------------------------- la guarda
    def test_el_ultimo_admin_no_puede_salir_del_rol(self):
        """No se puede dejar al sistema sin administrador activo: es la misma
        guarda que impide borrar a la última cuenta administradora."""
        self.admin.rol = Usuario.Rol.TECNICO
        self.admin.save(update_fields=["rol"])
        self.persona.rol = Usuario.Rol.ADMIN
        self.persona.save(update_fields=["rol"])
        self._encender(usuario=self.persona, guardista=self.persona)
        self.client.post(
            reverse("accounts:cambiar_rol"), {"rol": Usuario.Rol.USUARIO}
        )
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.rol, Usuario.Rol.ADMIN)
        self.assertContains(
            self.client.get(reverse("accounts:perfil")),
            "único administrador activo",
        )

    def test_un_admin_se_puede_ir_si_queda_otro(self):
        segundo = Usuario.objects.create_user(
            email="segundo@x.com", password="x", nombre="Segundo",
            rol=Usuario.Rol.ADMIN,
        )
        self.admin.rol = Usuario.Rol.TECNICO
        self.admin.save(update_fields=["rol"])
        self.persona.rol = Usuario.Rol.ADMIN
        self.persona.save(update_fields=["rol"])
        self._encender(usuario=self.persona, guardista=self.persona)
        self.client.post(
            reverse("accounts:cambiar_rol"), {"rol": Usuario.Rol.USUARIO}
        )
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.rol, Usuario.Rol.USUARIO)
        self.assertTrue(segundo.is_active)

    def test_la_casilla_no_da_paso_a_nadie_mas(self):
        """Quien no la tiene no puede llamar a la vista ni por URL directa."""
        self.client.logout()
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse("accounts:cambiar_rol"), {"rol": Usuario.Rol.USUARIO}
        )
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.rol, Usuario.Rol.ADMIN)
        self.assertEqual(respuesta.status_code, 302)
