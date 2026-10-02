"""Gráficas del panel y papelera de reciclaje.

Reproduce el caso del técnico: solo tiene tickets resueltos/cerrados, así que
las series que cuentan únicamente abiertas salían en blanco aunque tuviera
datos.
"""
import json
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Usuario
from apps.tickets.models import Categoria, Ticket
from apps.tickets.views import _build_tecnico_dashboard


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class SmokeTestCase(TestCase):
    """Base de las pruebas del panel.

    El proyecto sirve los estáticos con el manifest de WhiteNoise, que exige
    `collectstatic`; sin este override, renderizar base.html revienta con
    "Missing staticfiles manifest entry".
    """


class DashPiesTest(SmokeTestCase):
    def setUp(self):
        self.tecnico = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )
        self.client.force_login(self.tecnico)
        self.cat_a = Categoria.objects.create(grupo="SIESA", nombre="Facturación")
        self.cat_b = Categoria.objects.create(grupo="POS", nombre="Impresora")

    def _ticket(self, estado, prioridad, categoria, titulo="T"):
        t = Ticket.objects.create(
            titulo=titulo,
            descripcion="d",
            prioridad=prioridad,
            estado=estado,
            solicitante_nombre="User",
            categoria=categoria,
        )
        t.tecnico_asignado = self.tecnico
        t.save()
        return t

    def _dash(self):
        return json.loads(_build_tecnico_dashboard(self.tecnico.id))

    @staticmethod
    def _mapa(items):
        return {i["label"]: i["value"] for i in items}

    def test_solo_resueltos_no_deja_las_graficas_vacias(self):
        self._ticket(Ticket.Estado.RESUELTO, Ticket.Prioridad.BAJA, self.cat_b, "R1")
        self._ticket(Ticket.Estado.CERRADO, Ticket.Prioridad.ALTA, self.cat_a, "C1")
        d = self._dash()
        # por defecto (abiertas) no hay nada que mostrar
        self.assertEqual(d["pie_categoria"]["abiertas"], [])
        self.assertEqual(d["pie_prioridad"]["abiertas"], [])
        # pero "todas" ve los dos tickets
        cat = self._mapa(d["pie_categoria"]["todas"])
        self.assertEqual(sum(cat.values()), 2)
        self.assertIn("SIESA › Facturación", cat)
        self.assertIn("POS › Impresora", cat)
        pri = self._mapa(d["pie_prioridad"]["todas"])
        self.assertEqual(pri, {"Baja": 1, "Alta": 1})

    def test_cada_ambito_solo_muestra_su_estado(self):
        self._ticket(Ticket.Estado.ABIERTO, Ticket.Prioridad.URGENTE, self.cat_a, "A1")
        self._ticket(Ticket.Estado.EN_PROGRESO, Ticket.Prioridad.ALTA, self.cat_a, "P1")
        self._ticket(Ticket.Estado.RESUELTO, Ticket.Prioridad.BAJA, self.cat_b, "R1")
        self._ticket(Ticket.Estado.CERRADO, Ticket.Prioridad.MEDIA, self.cat_b, "C1")
        d = self._dash()
        # abiertas = abierto + en progreso (2 tickets, misma categoría)
        abiertas = self._mapa(d["pie_categoria"]["abiertas"])
        self.assertEqual(abiertas, {"SIESA › Facturación": 2})
        for ambito, cat in (("en_progreso", "SIESA › Facturación"),
                            ("cerrados", "POS › Impresora")):
            self.assertEqual(self._mapa(d["pie_categoria"][ambito]), {cat: 1}, ambito)
        # "Resueltas" agrupa lo ya terminado: resueltas Y cerradas, por eso
        # en esa categoría entran las dos (R1 resuelto y C1 cerrado).
        self.assertEqual(
            self._mapa(d["pie_categoria"]["resueltos"]), {"POS › Impresora": 2}
        )
        self.assertEqual(d["pie_categoria"]["eliminados"], [])
        self.assertEqual(len(self._mapa(d["pie_categoria"]["todas"])), 2)  # 2 categorías
        # por prioridad cada estado cae en su nivel
        self.assertEqual(self._mapa(d["pie_prioridad"]["abiertas"]), {"Urgente": 1, "Alta": 1})
        self.assertEqual(self._mapa(d["pie_prioridad"]["cerrados"]), {"Media": 1})
        self.assertEqual(
            self._mapa(d["pie_prioridad"]["resueltos"]), {"Baja": 1, "Media": 1}
        )

    def test_el_ambito_eliminados_solo_muestra_la_papelera(self):
        viva = self._ticket(Ticket.Estado.ABIERTO, Ticket.Prioridad.ALTA, self.cat_a, "Viva")
        muerta = self._ticket(Ticket.Estado.ABIERTO, Ticket.Prioridad.BAJA, self.cat_b, "Muerta")
        muerta.mandar_a_la_papelera(self.tecnico)
        d = self._dash()
        # el ticket de la papelera sale en "eliminadas" y en "todas", pero no
        # en los estados: ya no está en operación.
        self.assertEqual(self._mapa(d["pie_categoria"]["eliminados"]), {"POS › Impresora": 1})
        self.assertEqual(self._mapa(d["pie_categoria"]["abiertas"]), {"SIESA › Facturación": 1})
        self.assertEqual(len(self._mapa(d["pie_categoria"]["todas"])), 2)
        # el pivote y los KPIs nunca cuentan lo eliminado: la categoría del
        # ticket borrado ni siquiera aparece.
        filas = {f["label"]: f for f in d["pivot"]["dimensiones"]["categoria"]["rows"]}
        self.assertEqual(list(filas), ["SIESA › Facturación"])
        self.assertEqual(filas["SIESA › Facturación"]["total"], 1)
        self.assertEqual(d["papelera_total"], 1)
        self.assertFalse(viva.en_la_papelera)
        self.assertTrue(Ticket.objects.filter(pk=muerta.pk).exists() is False)
        self.assertTrue(Ticket.con_eliminados.filter(pk=muerta.pk).exists())

    def test_el_panel_ofrece_los_tres_desplegables(self):
        self._ticket(Ticket.Estado.RESUELTO, Ticket.Prioridad.BAJA, self.cat_b, "R1")
        url = reverse("tickets:panel_tecnico")
        resp = self.client.get(url, {"vista": "panel"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="wCatScope"')
        self.assertContains(resp, 'id="wPrioScope"')
        self.assertContains(resp, 'id="wCatLabel"')
        self.assertContains(resp, 'id="wPrioLabel"')
        self.assertContains(resp, 'id="wComp20"')
        # los tres desplegables ofrecen los seis ámbitos
        for valor in ("abiertas", "en_progreso", "resueltos", "cerrados", "eliminados", "todas"):
            self.assertContains(resp, f'value="{valor}"')
        for valor in ("recibidas", "completadas"):
            self.assertContains(resp, f'value="{valor}"')
        # y el JSON trae una serie por ámbito
        datos = json.loads(resp.context["dash_json"])
        for clave in ("abiertas", "en_progreso", "resueltos", "cerrados", "eliminados", "todas"):
            self.assertIn(clave, datos["pie_categoria"])
            self.assertIn(clave, datos["comparativo"])
        self.assertEqual(len(datos["comparativo"]["resueltos"]["ok"]), 20)


class DashSancionesAnsTest(SmokeTestCase):
    """`sla` debe traer las claves que panel-dash.js lee: vencidos / riesgo."""

    def setUp(self):
        self.tecnico = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )

    def _ticket(self, estado, titulo, ans_horas=8, duracion_horas=None):
        """ans_horas vive en la Categoria (en Ticket es propiedad)."""
        cat = Categoria.objects.create(
            grupo="SIESA", nombre=f"Cat {titulo}", ans_horas=ans_horas
        )
        t = Ticket.objects.create(
            titulo=titulo,
            descripcion="d",
            prioridad=Ticket.Prioridad.MEDIA,
            estado=estado,
            solicitante_nombre="User",
            categoria=cat,
        )
        t.tecnico_asignado = self.tecnico
        t.save()
        ahora = timezone.now()
        if duracion_horas is None:
            # abierto y con el limite ANS ya vencido
            Ticket.objects.filter(pk=t.pk).update(fecha_creacion=ahora - timedelta(days=3))
        else:
            # historia: creado hace 3 dias, cerrado despues de `duracion_horas`
            Ticket.objects.filter(pk=t.pk).update(
                fecha_creacion=ahora - timedelta(days=3),
                fecha_cierre=ahora - timedelta(days=3) + timedelta(hours=duracion_horas),
            )
        t.refresh_from_db()
        return t

    def _sla(self):
        datos = json.loads(_build_tecnico_dashboard(self.tecnico.id))
        return datos["sla"]["por_tecnico"]

    def test_las_claves_son_las_que_el_js_espera(self):
        self._ticket(Ticket.Estado.ABIERTO, "Vencido")
        filas = self._sla()
        self.assertEqual(len(filas), 1)
        # el JS lee r.vencidos y r.riesgo: si faltan, la grafica sale en blanco
        self.assertIn("vencidos", filas[0])
        self.assertIn("riesgo", filas[0])
        self.assertEqual(filas[0]["vencidos"], 1)
        self.assertEqual(filas[0]["riesgo"], 0)
        self.assertNotIn("por-vencer", filas[0])

    def test_resuelto_fuera_de_ans_es_sancion(self):
        # se cerro 48h despues con ANS de 8h: infraccion consumada
        self._ticket(Ticket.Estado.RESUELTO, "Tarde", ans_horas=8, duracion_horas=48)
        filas = self._sla()
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["vencidos"], 1)

    def test_resuelto_dentro_de_ans_no_cuenta(self):
        self._ticket(Ticket.Estado.RESUELTO, "A tiempo", ans_horas=24, duracion_horas=2)
        self.assertEqual(self._sla(), [])


class PapeleraTest(SmokeTestCase):
    """El borrado es lógico: se puede restaurar y no se pierde nada."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="ad@x.com", password="x", nombre="Ad", rol=Usuario.Rol.ADMIN
        )
        self.tecnico = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Tec", rol=Usuario.Rol.TECNICO
        )
        self.cat = Categoria.objects.create(grupo="SIESA", nombre="Impresora")
        self.ticket = Ticket.objects.create(
            titulo="Se va a la papelera",
            descripcion="d",
            prioridad=Ticket.Prioridad.MEDIA,
            estado=Ticket.Estado.ABIERTO,
            solicitante_nombre="User",
            solicitante_email="u@x.com",
            categoria=self.cat,
        )
        self.ticket.tecnico_asignado = self.tecnico
        self.ticket.save()

    def test_eliminar_manda_a_la_papelera_y_no_borra(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("tickets:eliminar", args=[self.ticket.pk]))
        self.assertEqual(resp.status_code, 302)
        # el ticket sigue existiendo, pero invisible para la operación
        self.assertTrue(Ticket.con_eliminados.filter(pk=self.ticket.pk).exists())
        self.assertFalse(Ticket.objects.filter(pk=self.ticket.pk).exists())
        t = Ticket.con_eliminados.get(pk=self.ticket.pk)
        self.assertIsNotNone(t.eliminado_en)
        self.assertEqual(t.eliminado_por, self.admin)

    def test_restaurar_lo_devuelve_a_la_operacion(self):
        self.ticket.mandar_a_la_papelera(self.admin)
        self.client.force_login(self.admin)
        self.client.post(reverse("tickets:restaurar", args=[self.ticket.pk]))
        self.assertTrue(Ticket.objects.filter(pk=self.ticket.pk).exists())
        t = Ticket.objects.get(pk=self.ticket.pk)
        self.assertIsNone(t.eliminado_en)

    def test_purgar_es_el_unico_borrado_definitivo(self):
        self.ticket.mandar_a_la_papelera(self.admin)
        self.client.force_login(self.admin)
        self.client.post(reverse("tickets:purgar", args=[self.ticket.pk]))
        self.assertFalse(Ticket.con_eliminados.filter(pk=self.ticket.pk).exists())

    def test_la_papelera_solo_la_ve_el_admin(self):
        self.ticket.mandar_a_la_papelera(self.admin)
        url = reverse("tickets:papelera")
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.ticket.codigo)
        self.assertEqual(resp.context["total"], 1)

    def test_el_ticket_eliminado_desaparece_de_la_lista_y_del_detalle(self):
        self.client.force_login(self.admin)
        self.ticket.mandar_a_la_papelera(self.admin)
        lista = self.client.get(reverse("tickets:lista"))
        self.assertNotContains(lista, self.ticket.codigo)
        self.assertEqual(
            self.client.get(reverse("tickets:detalle", args=[self.ticket.pk])).status_code, 404
        )

class CodigoTicketTest(SmokeTestCase):
    """El código es único en toda la base, papelera incluida."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="adm@x.com", password="x", nombre="Adm", rol=Usuario.Rol.ADMIN
        )

    def _crear(self, titulo="T"):
        return Ticket.objects.create(
            titulo=titulo, descripcion="d",
            solicitante_nombre="User", solicitante_email="u@x.com",
        )

    def test_el_codigo_nunca_reutiliza_el_de_un_ticket_eliminado(self):
        primero = self._crear("Primero")
        segundo = self._crear("Segundo")
        primero.mandar_a_la_papelera(self.admin)

        # El vivo sigue marcando el máximo, así que el nuevo no puede chocar.
        tercero = self._crear("Tercero")

        codigos = set(Ticket.con_eliminados.values_list("codigo", flat=True))
        self.assertEqual(len(codigos), 3)
        self.assertNotEqual(tercero.codigo, primero.codigo)
        self.assertEqual(tercero.codigo, "HD-0003")

    def test_se_puede_crear_despues_de_borrar_todo_el_historico(self):
        for i in range(3):
            self._crear(f"T{i}").mandar_a_la_papelera(self.admin)
        self.assertEqual(Ticket.objects.count(), 0)

        nuevo = self._crear("Nuevo")

        self.assertIsNotNone(nuevo.pk)
        self.assertEqual(nuevo.codigo, "HD-0004")
