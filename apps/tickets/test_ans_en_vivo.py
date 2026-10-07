"""El contador de ANS tiene que contar en vivo, y en todas las vistas.

Estas pruebas miran las dos cosas de las que depende el reloj:

1. Que el modelo le pase al navegador las dos horas que necesita (vencimiento y
   el momento en que el ANS pasa a "por vencer"), y que coincidan con el texto
   que ya calculaba el servidor.
2. Que cada vista que muestra el ANS mande esos datos en el HTML, para que el
   cronómetro de dogger.js pueda correr sin recargar la página.
"""

from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.tickets.models import Ticket

BASE = Path(__file__).resolve().parents[2]


def _crear_ticket(codigo, prioridad="normal", asignado=None, estado=Ticket.Estado.ABIERTO,
                  creado_hace=timedelta(hours=1), solicitante="persona@dogger.com.co"):
    """Ticket abierto cuya fecha decreation es la que se le indique."""
    t = Ticket(
        codigo=codigo,
        titulo=f"Prueba {codigo}",
        solicitante_nombre="Persona",
        solicitante_email=solicitante,
        prioridad=prioridad,
        tecnico_asignado=asignado,
        estado=estado,
    )
    t.save()
    # fecha_creacion es auto_now_add: para simular un ticket viejo hay que
    # escribirla después de creado, como hace la sincronización con GLPI.
    Ticket.objects.filter(pk=t.pk).update(
        fecha_creacion=timezone.now() - creado_hace,
        fecha_cierre=(
            timezone.now() - creado_hace + timedelta(hours=2)
            if estado in (Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO)
            else None
        ),
    )
    t.refresh_from_db()
    return t


class DatosAnsTest(TestCase):
    """Lo que el modelo le pasa al reloj tiene que ser coherente."""

    def test_abierto_entrega_limite_y_aviso(self):
        t = _crear_ticket("HD-1001")
        estado, texto, detalle, limite, aviso = t.datos_ans

        self.assertEqual(estado, "ok")
        self.assertTrue(texto.startswith("Faltan "))
        self.assertIsNotNone(detalle)
        self.assertEqual(limite, int(t.fecha_limite_ans.timestamp()))
        # El aviso es el límite menos el margen o menos dos horas, lo que
        # ocurra más tarde: nunca puede estar después del vencimiento.
        self.assertIsNotNone(aviso)
        self.assertLess(aviso, limite)
        self.assertGreater(aviso, limite - 3 * 3600)

    def test_vencido_no_trae_aviso_mayor_al_limite(self):
        # Muy anterior a cualquier ANS: tiene que estar vencido sí o sí.
        t = _crear_ticket("HD-1002", creado_hace=timedelta(days=60))
        estado, texto, _detalle, limite, aviso = t.datos_ans

        self.assertEqual(estado, "vencido")
        self.assertTrue(texto.startswith("ANS vencido"))
        self.assertEqual(limite, aviso)  # vencido: ya pasó el momento de aviso

    def test_info_ans_no_cambio(self):
        """info_ans sigue dando la misma tupla de siempre (estado, texto, detalle)."""
        t = _crear_ticket("HD-1003")
        self.assertEqual(t.info_ans, t.datos_ans[:3])

    def test_resuelto_no_lleva_reloj(self):
        t = _crear_ticket("HD-1004", estado=Ticket.Estado.RESUELTO)
        estado, texto, _detalle, limite, aviso = t.datos_ans

        self.assertEqual(estado, "resuelto")
        self.assertTrue(texto.startswith("Resuelto en"))
        self.assertIsNone(limite)
        self.assertIsNone(aviso)


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class AnsEnVivoEnLasVistasTest(TestCase):
    """Cada pantalla con contador de ANS debe Bringing el reloj consigo."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.usuario = User.objects.create_user("persona@dogger.com.co", "Persona", "x", rol="usuario")
        cls.tecnico = User.objects.create_user("tec@dogger.com.co", "Tecnico", "x", rol="tecnico")
        cls.admin = User.objects.create_user(
            "adm@dogger.com.co", "Admin", "x", rol="admin", is_staff=True, is_superuser=True
        )
        cls.ticket = _crear_ticket("HD-2001", asignado=cls.tecnico)
        cls.ticket_tecnico = _crear_ticket("HD-2002", asignado=cls.tecnico)
        cls.ticket_sin_tecnico = _crear_ticket("HD-2003")

    def _html(self, url, usuario):
        self.client.force_login(usuario)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        return r.content.decode("utf-8")

    def _exige_reloj(self, html, etiqueta):
        self.assertIn("data-ans-live", html, f"{etiqueta} no trae el reloj")
        self.assertIn("data-ans-limit=", html, f"{etiqueta} no trae la hora de vencimiento")
        self.assertIn("data-ans-aviso=", html, f"{etiqueta} no trae el aviso de vencimiento")

    def test_mi_panel(self):
        self._exige_reloj(self._html(reverse("tickets:mi_panel"), self.usuario), "Mi panel")

    def test_mi_ticket(self):
        self._exige_reloj(
            self._html(reverse("tickets:mi_ticket", args=[self.ticket.pk]), self.usuario),
            "Detalle en Mi panel",
        )

    def test_lista(self):
        self._exige_reloj(self._html(reverse("tickets:lista"), self.admin), "Lista")

    def test_sin_asignar(self):
        self._exige_reloj(self._html(reverse("tickets:sin_asignar"), self.admin), "Sin asignar")

    def test_detalle(self):
        self._exige_reloj(
            self._html(reverse("tickets:detalle", args=[self.ticket.pk]), self.admin),
            "Detalle del ticket",
        )

    def test_dashboard(self):
        self._exige_reloj(self._html(reverse("tickets:dashboard"), self.admin), "Dashboard")

    def test_panel_del_tecnico_mis_solicitudes(self):
        """La rejilla/listado de "mis solicitudes" del técnico."""
        self._exige_reloj(
            self._html(reverse("tickets:panel_tecnico") + "?vista=mis&mias=1", self.tecnico),
            "Mis solicitudes del técnico",
        )

    def test_el_reloj_conserva_el_formato_del_servidor(self):
        """El reloj repite el formato de formatear_duracion().

        Si el texto cambiara de forma al recargar ("1h 0min" un segundo y "1h"
        al recargar) se vería un salto tonto, así que se fija que las cuatro
        formas del reloj son las mismas del servidor.
        """
        js = (BASE / "static/js/dogger.js").read_text(encoding="utf-8")
        bloque = js[js.index("function duracion(seg) {"):]
        bloque = bloque[: bloque.index("\n    }")]

        for rama in ('d + "d " + h + "h"', 'd + "d"', 'h + "h " + m + "min"',
                     'h + "h"', 'm + "min"', 's + "s"'):
            self.assertIn(rama, bloque, f"el reloj perdió la forma {rama}")

        # El servidor usa estas mismas terminaciones.
        from apps.tickets.sla import formatear_duracion

        self.assertEqual(formatear_duracion(timedelta(hours=1)), "1h")
        self.assertEqual(formatear_duracion(timedelta(hours=26, minutes=15)), "1d 2h")
        self.assertEqual(formatear_duracion(timedelta(minutes=45)), "45min")

    def test_no_queda_el_cronometro_que_estaba_solo_en_el_panel(self):
        """El reloj es global: no puede quedar una copia dentro de una vista."""
        self.assertNotIn("data-ans-count", (BASE / "templates/tickets/panel_tecnico.html").read_text(encoding="utf-8"))
        js = (BASE / "static/js/dogger.js").read_text(encoding="utf-8")
        self.assertIn("Cronómetro del ANS", js)
        self.assertIn("[data-ans-live][data-ans-limit]", js)
