"""
Papelera del usuario + contador de abiertas de Mi panel.

Lo que se fija acá:

1. El solicitante puede cancelar (mandar a la papelera) sus solicitudes en
   cualquier estado y recuperarlas solo, sin pedirle nada a un administrador.
   Antes le daba 403 en `eliminar_ticket` y "solo mientras esté abierta" en el
   modal de Mi panel, así que sus solicitudes no se quitaban nunca y el
   contador de abiertas se quedaba clavado.
2. La papelera del usuario solo muestra lo suyo.
3. Lo que está en la papelera no cuenta como abierta.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.tickets.models import Ticket


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class PapeleraDelUsuario(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            "persona@dogger.com.co", "Persona", "dogger1234", rol="usuario",
        )
        cls.otro = get_user_model().objects.create_user(
            "otro@dogger.com.co", "Otro", "dogger1234", rol="usuario",
        )
        cls.admin = get_user_model().objects.create_user(
            "jefe@dogger.com.co", "Jefe", "dogger1234", rol="admin",
        )

    def ticket(self, codigo, estado=Ticket.Estado.ABIERTO, dueno=None):
        return Ticket.objects.create(
            codigo=codigo,
            titulo=f"Prueba {codigo}",
            solicitante_nombre="Persona",
            solicitante_email=(dueno or self.user).email,
            estado=estado,
        )

    # ---------- cancelar ----------
    def test_el_usuario_cancela_su_solicitud_desde_mi_panel(self):
        t = self.ticket("HD-1001")
        self.client.force_login(self.user)
        respuesta = self.client.post(
            reverse("tickets:mi_api_eliminar", args=[t.pk]), {"valor": "1"}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["ok"])
        t.refresh_from_db()
        self.assertTrue(t.en_la_papelera)

    def test_tambien_puede_cancelar_una_que_ya_esta_en_progreso(self):
        """Antes solo se podía cancelar con el ticket abierto."""
        t = self.ticket("HD-1002", estado=Ticket.Estado.EN_PROGRESO)
        self.client.force_login(self.user)
        respuesta = self.client.post(reverse("tickets:mi_api_eliminar", args=[t.pk]))
        self.assertEqual(respuesta.status_code, 200)
        t.refresh_from_db()
        self.assertTrue(t.en_la_papelera)

    def test_tampoco_puede_cancelar_la_solicitud_de_otro(self):
        t = self.ticket("HD-1003", dueno=self.otro)
        self.client.force_login(self.user)
        self.client.post(reverse("tickets:mi_api_eliminar", args=[t.pk]))
        t.refresh_from_db()
        self.assertFalse(t.en_la_papelera)

    def test_el_formulario_generico_tambien_lo_deja_cancelar(self):
        """La ruta de staff (formulario con next) ahora acepta al dueño."""
        t = self.ticket("HD-1004")
        self.client.force_login(self.user)
        self.client.post(reverse("tickets:eliminar", args=[t.pk]))
        t.refresh_from_db()
        self.assertTrue(t.en_la_papelera)

    # ---------- su papelera ----------
    def test_su_papelera_solo_muestra_lo_suyo(self):
        mia = self.ticket("HD-1005")
        mia.mandar_a_la_papelera(self.user)
        ajena = self.ticket("HD-1006", dueno=self.otro)
        ajena.mandar_a_la_papelera(self.otro)

        self.client.force_login(self.user)
        html = self.client.get(reverse("tickets:mi_papelera")).content.decode()
        self.assertIn("HD-1005", html)
        self.assertNotIn("HD-1006", html)

    def test_el_menu_muestra_cuantas_cancelo(self):
        """El enlace a su papelera siempre está, pero con morrito solo si hay algo."""
        self.client.force_login(self.user)
        vacia = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn(reverse("tickets:mi_papelera"), vacia)
        self.assertNotIn("solicitudes canceladas por ti", vacia)

        t = self.ticket("HD-1007")
        t.mandar_a_la_papelera(self.user)
        con_datos = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn("1 solicitudes canceladas por ti", con_datos)

    def test_restaura_su_solicitud_sin_ayuda_del_admin(self):
        t = self.ticket("HD-1008")
        t.mandar_a_la_papelera(self.user)
        self.client.force_login(self.user)
        self.client.post(reverse("tickets:restaurar", args=[t.pk]))
        t.refresh_from_db()
        self.assertFalse(t.en_la_papelera)

    def test_no_puede_restaurar_la_papelera_de_otro(self):
        t = self.ticket("HD-1009", dueno=self.otro)
        t.mandar_a_la_papelera(self.otro)
        self.client.force_login(self.user)
        self.client.post(reverse("tickets:restaurar", args=[t.pk]))
        t.refresh_from_db()
        self.assertTrue(t.en_la_papelera)

    def test_purga_definitiva_solo_del_propio(self):
        t = self.ticket("HD-1010")
        t.mandar_a_la_papelera(self.user)
        self.client.force_login(self.user)
        self.client.post(reverse("tickets:purgar", args=[t.pk]))
        self.assertFalse(Ticket.con_eliminados.filter(pk=t.pk).exists())

        ajena = self.ticket("HD-1011", dueno=self.otro)
        ajena.mandar_a_la_papelera(self.otro)
        self.client.post(reverse("tickets:purgar", args=[ajena.pk]))
        self.assertTrue(Ticket.con_eliminados.filter(pk=ajena.pk).exists())

    def test_el_admin_sigue_viendo_la_papelera_general(self):
        mia = self.ticket("HD-1012")
        mia.mandar_a_la_papelera(self.user)
        self.client.force_login(self.admin)
        html = self.client.get(reverse("tickets:papelera")).content.decode()
        self.assertIn("HD-1012", html)

    def test_al_cancelar_se_avisa_al_tecnico_asignado(self):
        """La solicitud se cancela de inmediato del lado de quien la atendia."""
        from apps.notificaciones.models import Notificacion

        tecnico = get_user_model().objects.create_user(
            "tecnico@dogger.com.co", "Tecnico", "x", rol="tecnico"
        )
        t = self.ticket("HD-1099")
        t.tecnico_asignado = tecnico
        t.save(update_fields=["tecnico_asignado"])

        self.client.force_login(self.user)
        self.client.post(reverse("tickets:mi_api_eliminar", args=[t.pk]))

        aviso = Notificacion.objects.filter(
            usuario=tecnico, clave=f"ticket:{t.pk}:cancelado:{tecnico.pk}"
        ).first()
        self.assertIsNotNone(aviso)
        self.assertIn("cancelado", aviso.titulo)
        self.assertFalse(aviso.leida)

    # ---------- el contador ----------
    def test_el_contador_marca_lo_nuevo_y_baja_al_revisarlo(self):
        """El morrito aparece cuando pasa algo y se limpia al entrar a mirarlo."""
        from apps.notificaciones import services as avisos

        t = self.ticket("HD-3000")
        self.client.force_login(self.user)

        # Sin novedades nuevas no hay contador.
        antes = self.client.get(reverse("notificaciones:api")).json()["no_leidas"]

        # Evento: el personal responde. El contador sube sin recargar, que es
        # como lo ve la campana con su refresco automático.
        avisos.ticket_cerrado(t)
        self.assertEqual(
            self.client.get(reverse("notificaciones:api")).json()["no_leidas"], antes + 1
        )

        # Al entrar a Mi panel ya está revisado: el contador vuelve a cero.
        self.client.get(reverse("tickets:mi_panel"))
        self.assertEqual(
            self.client.get(reverse("notificaciones:api")).json()["no_leidas"], 0
        )

    def test_cancelar_una_solicitud_no_cuenta_como_abierta(self):
        """La papelera no engaña: lo cancelado sale de la lista de solicitudes."""
        self.ticket("HD-3100")
        self.ticket("HD-3101")
        self.client.force_login(self.user)
        antes = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn("2 solicitudes", antes)

        objetivo = Ticket.objects.get(codigo="HD-3100")
        self.client.post(reverse("tickets:mi_api_eliminar", args=[objetivo.pk]))

        despues = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertIn("1 solicitud", despues)
        self.assertNotIn("HD-3100", despues)

    def test_lo_que_esta_en_la_papelera_no_cuenta(self):
        t = self.ticket("HD-4000")
        t.mandar_a_la_papelera(self.user)
        self.client.force_login(self.user)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertNotIn("HD-4000", html)
