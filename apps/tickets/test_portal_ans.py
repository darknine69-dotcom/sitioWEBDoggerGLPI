"""Prueba que la portada vuelve a explicar los tiempos ANS.

La sección «Cada categoría tiene un tiempo máximo de resolución (ANS)» vivía
en la portada y se perdió al remodelarla: el visitante veía que podíamos
reportar, pero no cuánto tardábamos. Aquí se comprueba que vuelve, con sus
cuatro desplegables y con las horas que de verdad manda `sla.py`, para que
lo prometido en la portada y lo que corre en el sistema no se contradigan.
"""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.tickets.sla import ANS_POR_PRIORIDAD


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class PortadaAnsTest(TestCase):
    def _portada(self):
        return self.client.get(reverse("tickets:portal"))

    def test_la_portada_trae_la_seccion_de_tiempos_ans(self):
        html = self._portada().content.decode()
        self.assertIn('id="compromisos"', html)
        self.assertIn("tiempo máximo de resolución (ANS)", html)

    def test_tiene_un_desplegable_por_prioridad(self):
        """Los cuatro desplegables existen y arrancan cerrados."""
        html = self._portada().content.decode()
        self.assertEqual(html.count('class="lp-ans-item'), 4)
        for nivel in ("p-urgente", "p-alta", "p-media", "p-baja"):
            self.assertIn(nivel, html)
        self.assertIn("<details", html)
        self.assertNotIn('class="lp-ans-item p-urgente" open', html)

    def test_cada_desplegable_explica_que_evalua_en_ese_nivel(self):
        """Abrirlo cuenta qué pasa en esa prioridad: reglas y ejemplos."""
        html = self._portada().content.decode()
        self.assertIn("El tiempo más corto: se atiende de inmediato", html)
        self.assertIn("serias limitaciones", html)
        self.assertIn("Afectación parcial", html)
        self.assertIn("Sin impacto en la venta", html)
        self.assertIn("la caja no abre", html)

    def test_las_horas_coinciden_con_el_sla_de_verdad(self):
        """La portada promete lo mismo que calcula el servidor.

        Si alguien cambia `ANS_POR_PRIORIDAD`, esta prueba avisa de que la
        portada quedó mintiendo.
        """
        html = self._portada().content.decode()
        for prioridad in ("urgente", "alta", "media", "baja"):
            horas = ANS_POR_PRIORIDAD[prioridad]
            self.assertIn(
                f"<p class=\"lp-ans-hours\">{horas}<span>h</span></p>", html,
                f"La portada no muestra {horas} h para la prioridad {prioridad}.",
            )

    def test_explica_que_el_tiempo_es_en_horas_habiles(self):
        html = self._portada().content.decode()
        self.assertIn("horas hábiles", html)

    def test_el_cronometro_del_ans_que_ya_hay_en_el_sistema_sigue_ahí(self):
        """La portada usa el mismo icono que el resto del sistema."""
        html = self._portada().content.decode()
        self.assertIn('id="i-stopwatch"', html)
        self.assertIn("#i-clock", html)

    def test_la_portada_sigue_sirviendo_para_reportar(self):
        """Restaurar la sección no movió el formulario de reporte."""
        respuesta = self._portada()
        self.assertContains(respuesta, 'id="compromisos"')
        self.assertContains(respuesta, 'id="como-funciona"')
        self.assertContains(respuesta, 'id="preguntas"')
