"""
Pulgar arriba / abajo a los técnicos + actividad GLPI como ajuste global.

Dos cosas que se(validaron) acá:

1. El bloque "Actividad reciente GLPI" se apaga para toda la mesa desde
   Ajustes → Configuración de la página, sin borrar ningún evento.
2. El modal de técnicos de Mi panel muestra quién está en la mesa, si está
   disponible y sus datos, y permite calificarlo una sola vez por persona.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Usuario
from apps.tickets.models import CalificacionTecnico, ConfigSitio, Ticket


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class AjusteGlobalActividadGlpi(TestCase):
    """El interruptor de Ajustes manda sobre todos los paneles."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            "persona@dogger.com.co", "Persona", "dogger1234", rol="usuario",
        )
        cls.admin = get_user_model().objects.create_user(
            "jefe@dogger.com.co", "Jefe", "dogger1234", rol="admin",
        )

    def test_la_actividad_glpi_se_ve_por_defecto(self):
        self.client.force_login(self.usuario)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn("Actividad reciente GLPI", html)

    def test_apagado_el_bloque_no_aparece_en_mi_panel(self):
        cfg = ConfigSitio.cargar()
        cfg.panel_mostrar_actividad_glpi = False
        cfg.save()
        self.client.force_login(self.usuario)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertNotIn("Actividad reciente GLPI", html)

    def test_apagado_el_bloque_no_aparece_en_el_dashboard(self):
        cfg = ConfigSitio.cargar()
        cfg.panel_mostrar_actividad_glpi = False
        cfg.save()
        html = self.client.get(reverse("tickets:dashboard")).content.decode()
        self.assertNotIn("Actividad GLPI", html)

    def test_ajustes_muestra_el_interruptor_solo_a_administradores(self):
        url = reverse("accounts:ajustes")
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(url), "panel_mostrar_actividad_glpi")

        self.client.force_login(self.usuario)
        self.assertNotContains(self.client.get(url), "panel_mostrar_actividad_glpi")

    def test_guardar_desde_ajustes_apaga_y_prende_el_bloque(self):
        url = reverse("accounts:configuracion_pagina")
        self.client.force_login(self.admin)

        # Interruptor apagado: llega el valor por defecto del campo oculto.
        self.client.post(url, {"ajustes_actividad_glpi": "1", "panel_mostrar_actividad_glpi": "0"})
        self.assertFalse(ConfigSitio.cargar().panel_mostrar_actividad_glpi)

        # Interruptor encendido: llega el valor "1" del checkbox.
        self.client.post(url, {"ajustes_actividad_glpi": "1", "panel_mostrar_actividad_glpi": "1"})
        self.assertTrue(ConfigSitio.cargar().panel_mostrar_actividad_glpi)

    def test_guardar_el_resto_de_la_config_no_prende_el_bloque_solo(self):
        """Al guardar la página sin tocar el interruptor, el bloque no cambia."""
        cfg = ConfigSitio.cargar()
        cfg.panel_mostrar_actividad_glpi = False
        cfg.save()

        self.client.force_login(self.admin)
        self.client.post(reverse("accounts:configuracion_pagina"), {"facebook_activo": "1"})
        self.assertFalse(ConfigSitio.cargar().panel_mostrar_actividad_glpi)


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ModalTecnicosActivos(TestCase):
    """El modal de Mi panel con los técnicos y su disponibilidad."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            "persona@dogger.com.co", "Persona", "dogger1234", rol="usuario",
        )
        cls.libre = get_user_model().objects.create_user(
            "libre@dogger.com.co", "Tecnico Libre", "dogger1234", rol="tecnico",
            telefono="3001112233", ubicacion="Bogotá",
        )
        cls.ocupado = get_user_model().objects.create_user(
            "ocupado@dogger.com.co", "Tecnico Ocupado", "dogger1234", rol="tecnico",
        )
        cls.inactivo = get_user_model().objects.create_user(
            "inactivo@dogger.com.co", "Tecnico Inactivo", "dogger1234",
            rol="tecnico", activo=False,
        )

    def test_lista_los_tecnicos_activos_con_sus_datos(self):
        self.client.force_login(self.usuario)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn("Técnicos activos", html)
        self.assertIn("Tecnico Libre", html)
        self.assertIn("Tecnico Ocupado", html)
        # Solo los activos del sistema.
        self.assertNotIn("Tecnico Inactivo", html)
        # Datos del técnico y disponibilidad.
        self.assertIn("libre@dogger.com.co", html)
        self.assertIn("3001112233", html)
        self.assertIn("Bogotá", html)
        self.assertIn("Disponible", html)

    def test_el_disponible_va_primero(self):
        from apps.tickets.services.tecnicos import mapeados_del_tecnico

        for i in range(5):
            Ticket.objects.create(
                codigo=f"HD-90{i}",
                titulo="Prueba de carga",
                solicitante_nombre="Persona",
                solicitante_email=self.usuario.email,
                estado=Ticket.Estado.ABIERTO,
                tecnico_asignado=self.ocupado,
            )
        lista = mapeados_del_tecnico(self.usuario)
        self.assertEqual([t["pk"] for t in lista], [self.libre.pk, self.ocupado.pk])
        self.assertEqual(lista[1]["estado"], "saturado")

    def test_un_tecnico_no_se_califica_a_si_mismo(self):
        from apps.tickets.services.tecnicos import mapeados_del_tecnico

        lista = mapeados_del_tecnico(self.libre)
        self.assertNotIn(self.libre.pk, [t["pk"] for t in lista])


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class CalificacionConPulgares(TestCase):
    """Votar con el pulgar arriba o abajo y verlo en el panel del técnico."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            "persona@dogger.com.co", "Persona", "dogger1234", rol="usuario",
        )
        cls.tecnico = get_user_model().objects.create_user(
            "tec@dogger.com.co", "Tecnico", "dogger1234", rol="tecnico",
        )
        cls.observador = get_user_model().objects.create_user(
            "obs@dogger.com.co", "Observador", "dogger1234", rol="observador",
        )

    def url(self):
        return reverse("tickets:calificar_tecnico", args=[self.tecnico.pk])

    def test_el_clic_del_pulgar_apunta_a_la_ruta_del_tecnico(self):
        """El JavaScript arma la ruta con el pk; se comprueba contra Django.

        La plantilla pone en data-calificar la ruta con un 0 de relleno y el
        clic cambia ese 0 por el pk del técnico. Si el trozo que se cambia no
        aparece en la ruta real, todos los votos se pierden en un 404 y los
        botones parecen muertos: esto lo ata para que no vuelva a pasar.
        """
        import re
        from pathlib import Path

        self.client.force_login(self.usuario)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        base = re.search(r'data-calificar="([^"]+)"', html).group(1)

        js = (Path(__file__).resolve().parents[2] / "static/js/voto-tecnicos.js").read_text(
            encoding="utf-8"
        )
        trozos = re.findall(r'\.replace\("([^"]+/0/)"', js)
        self.assertTrue(trozos, "el clic ya no cambia el pk de la ruta del voto")
        for trozo in trozos:
            armado = base.replace(trozo, "/tecnicos/" + str(self.tecnico.pk) + "/")
            self.assertNotEqual(armado, base, f"el trozo {trozo} no está en {base}")
            self.assertEqual(armado, self.url())

    def test_el_voto_por_ticket_manda_el_ticket_al_servidor(self):
        """Desde el detalle el clic tiene que enviar el ticket, no solo el valor."""
        from pathlib import Path

        js = (Path(__file__).resolve().parents[2] / "static/js/voto-tecnicos.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('lista.getAttribute("data-ticket")', js)
        self.assertIn("datos.ticket = ticket", js)

    def test_el_usuario_califica_y_queda_registrado(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(self.url(), {"valor": "1"})
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertTrue(datos["ok"])
        self.assertEqual(datos["mi_voto"], 1)
        self.assertEqual(datos["me_gusta"], 1)
        self.assertEqual(CalificacionTecnico.objects.count(), 1)

    def test_votar_otra_vez_quita_el_voto(self):
        self.client.force_login(self.usuario)
        self.client.post(self.url(), {"valor": "1"})
        datos = self.client.post(self.url(), {"valor": "1"}).json()
        self.assertEqual(datos["mi_voto"], 0)
        self.assertEqual(datos["me_gusta"], 0)
        self.assertEqual(CalificacionTecnico.objects.count(), 0)

    def test_cambiar_de_opinion_reemplaza_el_voto(self):
        self.client.force_login(self.usuario)
        self.client.post(self.url(), {"valor": "1"})
        datos = self.client.post(self.url(), {"valor": "-1"}).json()
        self.assertEqual(datos["mi_voto"], -1)
        self.assertEqual(datos["me_gusta"], 0)
        self.assertEqual(datos["no_me_gusta"], 1)
        self.assertEqual(CalificacionTecnico.objects.count(), 1)

    def test_cada_persona_vota_una_sola_vez(self):
        otro = get_user_model().objects.create_user(
            "otra@dogger.com.co", "Otra", "dogger1234", rol="usuario",
        )
        self.client.force_login(self.usuario)
        self.client.post(self.url(), {"valor": "1"})
        self.client.force_login(otro)
        self.client.post(self.url(), {"valor": "-1"})
        self.assertEqual(CalificacionTecnico.objects.count(), 2)

    def test_el_observador_no_califica(self):
        self.client.force_login(self.observador)
        respuesta = self.client.post(self.url(), {"valor": "1"})
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(CalificacionTecnico.objects.count(), 0)

    def test_no_se_califica_a_un_usuario_normal(self):
        """El endpoint solo acepta técnicos: con otro id responde 404."""
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse("tickets:calificar_tecnico", args=[self.usuario.pk]), {"valor": "1"}
        )
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(CalificacionTecnico.objects.count(), 0)

    def test_el_tecnico_ve_los_pulgares_en_su_panel(self):
        CalificacionTecnico.objects.create(
            tecnico=self.tecnico, usuario=self.usuario, valor=CalificacionTecnico.Valor.ME_GUSTA
        )
        CalificacionTecnico.objects.create(
            tecnico=self.tecnico,
            usuario=get_user_model().objects.create_user(
                "dos@dogger.com.co", "Dos", "dogger1234", rol="usuario"
            ),
            valor=CalificacionTecnico.Valor.ME_GUSTA,
        )
        CalificacionTecnico.objects.create(
            tecnico=self.tecnico,
            usuario=get_user_model().objects.create_user(
                "tres@dogger.com.co", "Tres", "dogger1234", rol="usuario"
            ),
            valor=CalificacionTecnico.Valor.NO_ME_GUSTA,
        )
        self.client.force_login(self.tecnico)
        html = self.client.get(reverse("tickets:panel_tecnico")).content.decode()
        self.assertIn("Tu calificación", html)
        # 2 de 3 votos: 67% de aprobación.
        self.assertIn("67% de aprobación", html)

    def test_sin_votos_el_panel_no_enseña_porcentaje(self):
        self.client.force_login(self.tecnico)
        html = self.client.get(reverse("tickets:panel_tecnico")).content.decode()
        self.assertIn("Tu calificación", html)
        self.assertIn("Todavía no hay votos", html)

    def test_tecnico_conectado_aparece_como_disponible(self):
        from apps.tickets.services.tecnicos import mapeados_del_tecnico

        self.tecnico.ultima_actividad = timezone.now()
        self.tecnico.save(update_fields=["ultima_actividad"])
        lista = mapeados_del_tecnico(self.usuario)
        self.assertEqual(lista[0]["estado"], "disponible")
        self.assertTrue(lista[0]["en_linea"])


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class TomarTicketTest(TestCase):
    """El botón Tomar de la Cola: sin asignar o de otro técnico.

    Si el ticket lo tiene otro técnico que no puede atenderlo, al tomarlo
    se reasigna y se dice a quién se le quitó. El propio no se toca.
    """

    def setUp(self):
        self.tec_a = Usuario.objects.create_user(
            email="teca@x.com", password="x", nombre="Tec A", rol=Usuario.Rol.TECNICO
        )
        self.tec_b = Usuario.objects.create_user(
            email="tecb@x.com", password="x", nombre="Tec B", rol=Usuario.Rol.TECNICO
        )

    def _ticket(self, codigo, tecnico=None):
        return Ticket.objects.create(
            codigo=codigo,
            titulo=f"T {codigo}",
            solicitante_nombre="Persona",
            solicitante_email="p@x.com",
            tecnico_asignado=tecnico,
        )

    def _tomar(self, ticket, tecnico):
        self.client.force_login(tecnico)
        return self.client.post(
            reverse("tickets:panel_tecnico_tomar", args=[ticket.pk])
        )

    def test_tomar_sin_asignar(self):
        t = self._ticket("HD-7001")
        respuesta = self._tomar(t, self.tec_b)
        self.assertEqual(respuesta.status_code, 302)
        t.refresh_from_db()
        self.assertEqual(t.tecnico_asignado, self.tec_b)

    def test_tomar_de_otro_tecnico_reasigna(self):
        t = self._ticket("HD-7002", tecnico=self.tec_a)
        self.client.force_login(self.tec_b)
        respuesta = self.client.post(
            reverse("tickets:panel_tecnico_tomar", args=[t.pk]), follow=True
        )
        t.refresh_from_db()
        self.assertEqual(t.tecnico_asignado, self.tec_b)
        mensajes = " ".join(
            m.message for m in respuesta.context["messages"]
        )
        self.assertIn("antes lo tenía Tec A", mensajes)

    def test_tomar_propio_no_hace_nada(self):
        t = self._ticket("HD-7003", tecnico=self.tec_a)
        self.client.force_login(self.tec_a)
        respuesta = self.client.post(
            reverse("tickets:panel_tecnico_tomar", args=[t.pk]), follow=True
        )
        t.refresh_from_db()
        self.assertEqual(t.tecnico_asignado, self.tec_a)
        mensajes = " ".join(
            m.message for m in respuesta.context["messages"]
        )
        self.assertIn("ya está asignado a ti", mensajes)

    def test_cola_muestra_tomar_en_los_que_no_son_mios(self):
        ajeno = self._ticket("HD-7004", tecnico=self.tec_a)
        mio = self._ticket("HD-7005", tecnico=self.tec_b)
        self.client.force_login(self.tec_b)
        html = self.client.get(
            reverse("tickets:panel_tecnico"), {"vista": "cola"}
        ).content.decode()
        url_ajeno = reverse("tickets:panel_tecnico_tomar", args=[ajeno.pk])
        url_mio = reverse("tickets:panel_tecnico_tomar", args=[mio.pk])
        self.assertIn(url_ajeno, html)
        self.assertNotIn(url_mio, html)
