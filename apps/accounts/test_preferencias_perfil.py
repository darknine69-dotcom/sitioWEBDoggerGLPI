from unittest.mock import patch
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.notificaciones.models import Notificacion
from apps.notificaciones.services import crear


class PreferenciasPerfilTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            email="perfil@example.com", nombre="Perfil", password="clave12345", rol="usuario"
        )
        self.client.force_login(self.usuario)

    def test_cierre_inactividad_configuracion_y_validacion(self):
        url = reverse("accounts:configurar_cierre_inactividad")
        self.assertEqual(self.client.post(url, {"habilitado": "1", "minutos": "0"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"habilitado": "1", "minutos": "5"}).status_code, 200)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.preferencias_notificaciones["cierre_inactividad"])
        self.assertEqual(self.usuario.preferencias_notificaciones["cierre_inactividad_minutos"], 5)

    def test_cierre_inactividad_no_se_renueva_con_consultas_automaticas(self):
        self.usuario.preferencias_notificaciones = {"cierre_inactividad": True, "cierre_inactividad_minutos": 5}
        self.usuario.save(update_fields=["preferencias_notificaciones"])
        sesion = self.client.session
        sesion["ultima_actividad_usuario"] = 1000
        sesion.save()
        url = reverse("accounts:actividad_sesion")
        with patch("time.time", return_value=1299):
            self.assertEqual(self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 200)
        with patch("time.time", return_value=1300):
            self.assertEqual(self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 401)

    def test_consulta_automatica_html_no_reinicia_inactividad(self):
        self.usuario.preferencias_notificaciones = {"cierre_inactividad": True, "cierre_inactividad_minutos": 5}
        self.usuario.save(update_fields=["preferencias_notificaciones"])
        sesion = self.client.session
        sesion["ultima_actividad_usuario"] = 1000
        sesion.save()
        with patch("time.time", return_value=1299):
            self.client.get(reverse("accounts:actividad_sesion"), HTTP_ACCEPT="text/html")
        with patch("time.time", return_value=1300):
            self.assertEqual(self.client.get(reverse("accounts:actividad_sesion"), HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 401)

    def test_interaccion_renueva_y_opcion_desactivada_no_expira(self):
        self.usuario.preferencias_notificaciones = {"cierre_inactividad": True, "cierre_inactividad_minutos": 5}
        self.usuario.save(update_fields=["preferencias_notificaciones"])
        sesion = self.client.session
        sesion["ultima_actividad_usuario"] = 1000
        sesion.save()
        url = reverse("accounts:actividad_sesion")
        with patch("time.time", return_value=1299):
            self.assertEqual(self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 200)
        with patch("time.time", return_value=1400):
            self.assertEqual(self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 200)
        self.usuario.preferencias_notificaciones["cierre_inactividad"] = False
        self.usuario.save(update_fields=["preferencias_notificaciones"])
        with patch("time.time", return_value=9999):
            self.assertEqual(self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 200)

    @patch("apps.accounts.views._glpi_available", return_value=False)
    def test_guardar_y_aplicar_preferencias_individuales(self, _glpi):
        respuesta = self.client.post(reverse("accounts:ajustes"), {
            "guardar_notificaciones": "1", "tickets_nuevos": "1", "eventos": "1",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.preferencias_notificaciones["recordatorios"])
        self.assertIsNone(crear(self.usuario, Notificacion.Tipo.TICKET_RECORDATORIO, "Plazo", "Aviso"))
        self.assertIsNotNone(crear(self.usuario, Notificacion.Tipo.TICKET_NUEVO, "Ticket", "Aviso"))

    @patch("apps.accounts.views._glpi_available", return_value=False)
    def test_ajustes_guardan_correos_y_campana_independientemente(self, _glpi):
        respuesta = self.client.post(reverse("accounts:ajustes"), {
            "guardar_notificaciones": "1", "incluir_preferencias_correo": "1",
            "tickets_nuevos": "1", "correo_ans": "1", "correo_resumen": "1",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.usuario.refresh_from_db()
        prefs = self.usuario.preferencias_notificaciones
        self.assertTrue(prefs["tickets_nuevos"])
        self.assertFalse(prefs["correo_tickets"])
        self.assertTrue(prefs["correo_ans"])
        self.assertTrue(prefs["correo_resumen"])
        self.assertContains(self.client.get(reverse("accounts:ajustes")), 'name="correo_resumen" value="1" checked')

    @patch("apps.accounts.views._glpi_available", return_value=False)
    def test_foto_se_guarda_y_se_puede_leer_en_almacenamiento_aislado(self, _glpi):
        from PIL import Image
        contenido = BytesIO()
        Image.new("RGB", (10, 10), "red").save(contenido, format="PNG")
        with TemporaryDirectory() as carpeta, override_settings(MEDIA_ROOT=carpeta):
            respuesta = self.client.post(reverse("accounts:ajustes"), {
                "nombre": self.usuario.nombre, "email": self.usuario.email,
                "avatar": SimpleUploadedFile("perfil.png", contenido.getvalue(), content_type="image/png"),
            })
            self.assertEqual(respuesta.status_code, 302)
            self.usuario.refresh_from_db()
            self.assertTrue(self.usuario.avatar.storage.exists(self.usuario.avatar.name))
            with self.usuario.avatar.open("rb") as foto:
                self.assertTrue(foto.read().startswith(b"\x89PNG"))

    @patch("apps.accounts.views._glpi_available", return_value=False)
    @patch("apps.accounts.forms.PerfilForm.save", side_effect=OSError("storage unavailable"))
    def test_error_de_almacenamiento_se_muestra_sin_confirmar_exito(self, _guardar, _glpi):
        respuesta = self.client.post(reverse("accounts:ajustes"), {
            "nombre": self.usuario.nombre, "email": self.usuario.email,
        })
        self.assertContains(respuesta, "No se pudo guardar la foto")

    @patch("apps.accounts.views._glpi_available", return_value=False)
    def test_preferencia_correo_persiste_y_ajustes_campana_la_conserva(self, _glpi):
        respuesta = self.client.post(reverse("accounts:preferencias_correo"), {"clave": "correo_tickets", "valor": "0"})
        self.assertEqual(respuesta.status_code, 200)
        self.client.post(reverse("accounts:ajustes"), {"guardar_notificaciones": "1", "eventos": "1"})
        self.usuario.refresh_from_db()
        self.assertIs(self.usuario.preferencias_notificaciones["correo_tickets"], False)
        self.assertTrue(self.usuario.preferencias_notificaciones["eventos"])

    def test_preferencias_requieren_csrf_y_rechazan_claves_ajenas(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        self.assertEqual(cliente.post(reverse("accounts:preferencias_correo"), {"clave": "correo_tickets", "valor": "0"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("accounts:preferencias_correo"), {"clave": "otro", "valor": "0"}).status_code, 400)

    def test_idioma_perfil_persiste_y_traduce_seccion_general(self):
        url = reverse("accounts:preferencias_correo")
        self.assertEqual(self.client.post(url, {"clave": "idioma_perfil", "valor": "en"}).status_code, 200)
        self.assertContains(self.client.get(reverse("accounts:perfil")), "General preferences")
        self.assertEqual(self.client.post(url, {"clave": "idioma_perfil", "valor": "pt"}).status_code, 200)
        self.assertContains(self.client.get(reverse("accounts:perfil")), "Preferências gerais")
        self.assertEqual(self.client.post(url, {"clave": "idioma_perfil", "valor": "xx"}).status_code, 400)

    @override_settings(EMAIL_HOST_USER="smtp@example.invalid", DOGGER_FONDO_ASINCRONO=False)
    @patch("apps.tickets.services.fondo.en_fondo", return_value=1)
    def test_envio_filtra_destinatarios_segun_preferencia_individual(self, enviar):
        from apps.notificaciones.emails import _enviar
        otro = get_user_model().objects.create_user(email="otro@example.com", nombre="Otro", password="x", rol="usuario")
        self.usuario.preferencias_notificaciones = {"correo_tickets": False, "correo_ans": True}
        self.usuario.save(update_fields=["preferencias_notificaciones"])
        self.assertTrue(_enviar("Asunto", "Texto", "HTML", [self.usuario.email, otro.email], preferencia="correo_tickets"))
        self.assertEqual(enviar.call_args.args[4], [otro.email])
        enviar.reset_mock()
        self.assertTrue(_enviar("Asunto", "Texto", "HTML", [self.usuario.email], preferencia="correo_tickets"))
        enviar.assert_not_called()
        self.assertTrue(_enviar("ANS", "Texto", "HTML", [self.usuario.email], preferencia="correo_ans"))
        enviar.assert_called_once()

    @override_settings(EMAIL_HOST_USER="smtp@example.invalid")
    @patch("apps.tickets.services.fondo.en_fondo", return_value=1)
    def test_correo_de_comentarios_respeta_preferencia(self, enviar):
        from apps.tickets.notifications import _enviar

        self.usuario.preferencias_notificaciones = {"correo_tickets": False}
        self.usuario.save(update_fields=["preferencias_notificaciones"])
        _enviar("Comentario", "Texto", [self.usuario.email])
        enviar.assert_not_called()

    @patch("apps.accounts.views._glpi_available", return_value=False)
    def test_perfil_solo_muestra_tickets_del_usuario(self, _glpi):
        respuesta = self.client.get(reverse("accounts:ajustes"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["perfil_ticket_total"], 0)
        self.assertNotIn("perfil_categoria_total", respuesta.context)

    @patch("apps.accounts.views._glpi_available", return_value=False)
    def test_ajustes_disponibles_y_opciones_por_rol(self, _glpi):
        for rol in ("usuario", "tecnico", "admin", "observador"):
            with self.subTest(rol=rol):
                cuenta = get_user_model().objects.create_user(
                    email=f"{rol}@example.com", nombre=rol, password="clave12345", rol=rol
                )
                self.client.force_login(cuenta)
                respuesta = self.client.get(reverse("accounts:ajustes"))
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, "Información personal")
                self.assertContains(respuesta, "Guardar preferencias")
                self.assertEqual("perfil_categoria_total" in respuesta.context, rol == "admin")
