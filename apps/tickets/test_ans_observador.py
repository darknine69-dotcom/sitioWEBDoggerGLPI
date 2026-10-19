"""Prueba el ANS del observador: el cronómetro en pantalla y el aviso.

Hay dos cosas distintas que se prueban aquí, y las dos se apoyan en la misma
decisión del servidor (`Ticket.datos_ans`):

  1. Que el observador vea, sin tener que abrir cada ticket, cuál se le está
     yendo del plazo: indicador, sección «Por vencer» con el cronómetro
     corriendo, y la ventana que explica qué significa todo eso.
  2. Que al entrar se avise una sola vez a cada responsable: correo al
     técnico y a la persona que abrió el ticket, campana al observador que
     supervisa. Con el interruptor de alertas de la zona apagado no se avisa
     a nadie.
"""

from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Usuario
from apps.notificaciones.models import Notificacion
from apps.tickets import ans_avisos
from apps.tickets.models import ElementoMiLista, Ticket, ZonaObservador

# La prioridad media tiene 12 h de ANS: así se llega justo al aviso o al
# vencimiento sin tener que tocar la categoría.
HORAS_MEDIA = 12


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class BaseAnsTest(TestCase):
    """Arma el caso mínimo: un observador, una persona de su lista en una
    zona con alertas, un técnico y un ticket abierto."""

    def setUp(self):
        self.observador = Usuario.objects.create_user(
            email="obs@x.com", password="x", nombre="Obs",
            rol=Usuario.Rol.OBSERVADOR,
        )
        self.tecnico = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Técnico Uno",
            rol=Usuario.Rol.TECNICO,
        )
        self.solicitante = Usuario.objects.create_user(
            email="ana@x.com", password="x", nombre="Ana",
            rol=Usuario.Rol.USUARIO,
        )
        self.zona = ZonaObservador.objects.create(
            observador=self.observador, nombre="Sede norte", alertas_ans=True
        )
        ElementoMiLista.objects.create(
            observador=self.observador, usuario=self.solicitante,
            usuario_email="ana@x.com", zona=self.zona,
        )
        # Crear usuarios deja su bienvenida en el buzón; no es lo que se
        # prueba aquí, así que se limpia para que los conteos sean solo del ANS.
        mail.outbox.clear()
        self.client.force_login(self.observador)

    def _avisos_ans(self):
        """Los avisos de campana del ANS, sin mezclarlos con otros avisos."""
        return Notificacion.objects.filter(clave__startswith="ans-")

    def _envejecer(self, ticket, horas):
        """Deja el ticket con el ANS `horas` más cerca de vencer.

        `fecha_creacion` es auto_now_add, así que se corrige con un update
        directo y no se puede desde el objeto recién creado.
        """
        Ticket.objects.filter(pk=ticket.pk).update(
            fecha_creacion=timezone.now() - timedelta(hours=horas)
        )
        ticket.refresh_from_db()
        return ticket

    def _ticket(self, tecnico=None, horas=None, prioridad=Ticket.Prioridad.MEDIA,
                estado=Ticket.Estado.ABIERTO):
        ticket = Ticket.objects.create(
            titulo="Impresora del mostrador sin papel",
            descripcion="No saca nada.",
            prioridad=prioridad,
            estado=estado,
            solicitante_nombre="Ana",
            solicitante_email="ana@x.com",
            solicitante_punto="Punto 1",
            tecnico_asignado=tecnico if tecnico is not None else self.tecnico,
        )
        if horas is not None:
            self._envejecer(ticket, horas)
        # Crear el ticket dispara su propio aviso de "ticket nuevo"; no es lo
        # que se prueba aquí, así que el buzón arranca limpio de ANS.
        mail.outbox.clear()
        return ticket


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ObservadorVeElAnsTest(BaseAnsTest):
    """El observador ve los tiempos ANS sin abrir cada ticket."""

    def _monitoreo(self):
        return self.client.get(reverse("tickets:obs_monitoreo"))

    def test_el_cronometro_existe_en_el_sprite(self):
        """El icono de cronómetro está en el sprite de la base."""
        html = self._monitoreo().content.decode()
        self.assertIn('id="i-stopwatch"', html)

    def test_tickets_recientes_llevan_el_cronometro(self):
        """La lista de tickets recientes muestra el ANS con su reloj vivo."""
        ticket = self._ticket(horas=HORAS_MEDIA - 0.5)
        html = self._monitoreo().content.decode()
        self.assertIn("data-ans-live", html)
        self.assertIn('class="ans-time ans-por-vencer', html)
        self.assertIn('href="#i-stopwatch"', html)
        self.assertIn(ticket.codigo, html)

    def test_el_reloj_lleva_las_dos_fechas_que_necesita_el_javascript(self):
        """`data-ans-limit` y `data-ans-aviso` salen en el HTML: sin ellos el
        reloj no podría seguir contando sin recargar."""
        ticket = self._ticket(horas=HORAS_MEDIA - 0.5)
        respuesta = self._monitoreo()
        estado, _texto, _detalle, limite, aviso = ticket.datos_ans
        self.assertEqual(estado, "por-vencer")
        self.assertContains(respuesta, f'data-ans-limit="{limite}"')
        self.assertContains(respuesta, f'data-ans-aviso="{aviso}"')

    def test_indicador_de_por_vencer_en_la_fila_de_arriba(self):
        self._ticket(horas=HORAS_MEDIA - 0.5)
        self._ticket(horas=HORAS_MEDIA + 2, prioridad=Ticket.Prioridad.URGENTE)
        html = self._monitoreo().content.decode()
        self.assertIn('class="dash-stat dash-hov-ans"', html)
        self.assertIn("Por vencer", html)
        # Dos avisos: uno por vencer y uno ya vencido.
        self.assertIn('class="dash-stat-value st-ans">2<', html)

    def test_seccion_por_vencer_con_su_ficha_y_su_accion(self):
        """La sección enseña el caso, quién lo pidió, quién atiende y deja
        presionar al técnico ahí mismo, sin salir de la página."""
        ticket = self._ticket(horas=HORAS_MEDIA - 0.5)
        respuesta = self._monitoreo()
        self.assertContains(respuesta, 'id="por-vencer"')
        self.assertContains(respuesta, ticket.codigo)
        self.assertContains(respuesta, "Impresora del mostrador sin papel")
        self.assertContains(respuesta, "Ana")
        self.assertContains(respuesta, "Técnico Uno")
        self.assertContains(respuesta, reverse("tickets:obs_presionar", args=[ticket.pk]))

    def _seccion_por_vencer(self, html):
        """Lo que dice la sección, por dentro."""
        return html.split('id="por-vencer"')[1].split("</section>")[0]

    def test_sin_nada_por_vencer_no_se_enseña(self):
        """Con el ANS todavía holgado no hay caso que enseñar. La sección
        sigue estando (el indicador de arriba apunta a ella) pero vacía."""
        self._ticket(horas=2)
        html = self._monitoreo().content.decode()
        seccion = self._seccion_por_vencer(html)
        self.assertNotIn("HD-", seccion)
        self.assertIn("Ninguno de los tickets", seccion)
        self.assertIn('class="dash-stat-value st-ans">0<', html)

    def test_un_ticket_resuelto_no_entra(self):
        """Resuelto ya no tiene ANS que vigilar, aunque fuera viejo."""
        self._ticket(
            horas=HORAS_MEDIA + 5,
            estado=Ticket.Estado.RESUELTO,
        )
        html = self._monitoreo().content.decode()
        seccion = self._seccion_por_vencer(html)
        self.assertNotIn("HD-", seccion)
        self.assertIn("Ninguno de los tickets", seccion)

    def test_el_aviso_respeta_el_interruptor_de_la_zona(self):
        """Con las alertas de la zona apagadas la sección no se llena: no
        enseña ningún caso ni el aviso de los que sí vencerían."""
        self.zona.alertas_ans = False
        self.zona.save(update_fields=["alertas_ans"])
        self._ticket(horas=HORAS_MEDIA - 0.5)
        html = self._monitoreo().content.decode()
        seccion = self._seccion_por_vencer(html)
        self.assertNotIn("HD-", seccion)
        self.assertIn("Ninguno de los tickets", seccion)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class VentanaDelAnsTest(BaseAnsTest):
    """La etiqueta del cronómetro explica lo que está diciendo."""

    def _monitoreo(self):
        return self.client.get(reverse("tickets:obs_monitoreo"))

    def test_las_etiquetas_abren_la_ventana(self):
        """Cada etiqueta es un botón que lleva los datos a la ventana."""
        self._ticket(horas=HORAS_MEDIA - 0.5)
        html = self._monitoreo().content.decode()
        self.assertIn('id="ansModal"', html)
        self.assertIn("data-ans-info", html)
        self.assertIn('data-ans-horas="12"', html)
        self.assertIn('data-ans-tecnico="Técnico Uno"', html)

    def test_la_ventana_explica_que_es_el_ans(self):
        html = self._monitoreo().content.decode()
        self.assertIn("Acuerdo de Nivel de Servicio", html)
        # La leyenda de los tres colores, que es lo que resuelve la duda.
        self.assertIn("Dentro de plazo", html)
        self.assertIn("Por vencer", html)
        self.assertIn("Vencido", html)

    def test_la_ventana_da_el_plazo_y_quien_responde(self):
        html = self._monitoreo().content.decode()
        self.assertIn("Plazo ANS", html)
        self.assertIn("Límite", html)
        self.assertIn("Quién responde", html)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class AvisoDeAnsTest(BaseAnsTest):
    """Al entrar se avisa una sola vez a cada responsable."""

    def _entrar(self):
        return self.client.get(reverse("tickets:obs_monitoreo"))

    def test_avisa_al_tecnico_y_a_quien_abrio_el_ticket(self):
        self._ticket(horas=HORAS_MEDIA - 0.5)
        self._entrar()
        correos = {c.to[0] for c in mail.outbox}
        self.assertEqual(correos, {"tec@x.com", "ana@x.com"})
        tecnico = [c for c in mail.outbox if c.to == ["tec@x.com"]][0]
        self.assertIn("Por vencer", tecnico.subject)
        self.assertIn("HD-", tecnico.subject)
        self.assertIn("ANS", tecnico.body)

    def test_avisa_al_observador_por_campana(self):
        ticket = self._ticket(horas=HORAS_MEDIA - 0.5)
        self._entrar()
        aviso = Notificacion.objects.get(
            usuario=self.observador, clave=f"ans-{ticket.pk}"
        )
        self.assertIn(ticket.codigo, aviso.titulo)
        self.assertEqual(aviso.icono, "i-stopwatch")
        self.assertIn("/observador/monitoreo/", aviso.url)
        self.assertIn("por-vencer", aviso.url)

    def test_solo_se_avisa_una_vez(self):
        """La segunda pasada no repite nada: correo ni campana."""
        self._ticket(horas=HORAS_MEDIA - 0.5)
        self._entrar()
        correos = len(mail.outbox)
        avisos = self._avisos_ans().count()
        self._entrar()
        self.assertEqual(len(mail.outbox), correos)
        self.assertEqual(self._avisos_ans().count(), avisos)

    def test_pero_el_listado_sigue_mostrando_lo_ya_avisado(self):
        """Avisado no es lo mismo que resuelto: el caso sigue en pantalla."""
        self._ticket(horas=HORAS_MEDIA - 0.5)
        self._entrar()
        self._entrar()
        self.assertIn('id="por-vencer"', self._entrar().content.decode())

    def test_con_las_alertas_apagadas_no_se_manda_nada(self):
        self.zona.alertas_ans = False
        self.zona.save(update_fields=["alertas_ans"])
        self._ticket(horas=HORAS_MEDIA - 0.5)
        self._entrar()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self._avisos_ans().count(), 0)

    def test_quien_esta_sin_zona_no_recibe_el_aviso(self):
        """Sin carpeta que decida, no hay alerta: así lo manda el formulario
        del observador, que también pide poner zona."""
        ElementoMiLista.objects.filter(observador=self.observador).update(zona=None)
        self._ticket(horas=HORAS_MEDIA - 0.5)
        self._entrar()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self._avisos_ans().count(), 0)

    def test_el_comando_de_cron_manda_lo_que_falta(self):
        """El cron no depende de que el observador entre a la página."""
        self._ticket(horas=HORAS_MEDIA - 0.5)
        salida = StringIO()
        call_command("avisar_ans_por_vencer", stdout=salida)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Avisado 1 ticket.", salida.getvalue())
        self.assertTrue(self._avisos_ans().filter(usuario=self.observador).exists())

    def test_el_comando_seco_no_manda_nada(self):
        """--seco lista lo que mandaría sin tocar el buzón."""
        self._ticket(horas=HORAS_MEDIA - 0.5)
        salida = StringIO()
        call_command("avisar_ans_por_vencer", "--seco", stdout=salida)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("por avisar", salida.getvalue())
        self.assertIn("no se mandó nada", salida.getvalue())

    def test_el_comando_no_se_queja_cuando_no_hay_nada(self):
        self._ticket(horas=2)
        salida = StringIO()
        call_command("avisar_ans_por_vencer", stdout=salida)
        self.assertIn("Ningún ticket por vencer sin avisar.", salida.getvalue())

    def test_lo_que_ya_se_avisó_el_comando_lo_deja_en_paz(self):
        self._ticket(horas=HORAS_MEDIA - 0.5)
        call_command("avisar_ans_por_vencer", stdout=StringIO())
        call_command("avisar_ans_por_vencer", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 2)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ReglaDelUmbralTest(BaseAnsTest):
    """El aviso usa el mismo umbral que la etiqueta: ninguno de los dos
    puede decir algo distinto delante del usuario."""

    def test_con_tiempo_de_sobra_es_ok_y_no_se_avisa(self):
        ticket = self._ticket(horas=2)
        estado, texto, _detalle = ticket.info_ans
        self.assertEqual(estado, "ok")
        self.assertTrue(texto.startswith("Faltan"))
        self.assertEqual(ans_avisos.por_vencer(), [])

    def test_a_dos_horas_del_limite_es_por_vencer(self):
        ticket = self._ticket(horas=HORAS_MEDIA - 1.5)
        self.assertEqual(ticket.info_ans[0], "por-vencer")
        self.assertEqual([t.pk for t in ans_avisos.por_vencer()], [ticket.pk])

    def test_despues_del_limite_es_vencido(self):
        ticket = self._ticket(horas=HORAS_MEDIA + 1)
        self.assertEqual(ticket.info_ans[0], "vencido")
        self.assertEqual(ans_avisos.por_vencer()[0].ans_estado, "vencido")

    def test_los_vencidos_salen_primero(self):
        tarde = self._ticket(horas=HORAS_MEDIA + 1)
        temprano = self._ticket(horas=HORAS_MEDIA + 6)
        self.assertEqual(
            [t.pk for t in ans_avisos.por_vencer()], [temprano.pk, tarde.pk]
        )
