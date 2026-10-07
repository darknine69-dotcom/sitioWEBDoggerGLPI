"""
Calificar técnicos desde el detalle de un ticket.

La lista aparece debajo de Propiedades, sin modal: acá el voto queda atado a
ese ticket y cada fila trae la barra de aprobación contada sobre tickets
resueltos.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.tickets.models import CalificacionTecnico, Ticket


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class CalificarDesdeElDetalle(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            "persona@dogger.com.co", "Persona", "dogger1234", rol="usuario",
        )
        cls.otro = get_user_model().objects.create_user(
            "otro@dogger.com.co", "Otro", "dogger1234", rol="usuario",
        )
        cls.tecnico = get_user_model().objects.create_user(
            "tec@dogger.com.co", "Tecnico", "dogger1234", rol="tecnico",
        )
        cls.ayudante = get_user_model().objects.create_user(
            "ayuda@dogger.com.co", "Ayudante", "dogger1234", rol="tecnico",
        )
        cls.observador = get_user_model().objects.create_user(
            "obs@dogger.com.co", "Observador", "dogger1234", rol="observador",
        )

    def ticket(self, **extra):
        datos = {
            "titulo": "Impresora sin papel",
            "descripcion": "No imprime",
            "solicitante_nombre": "Persona",
            "solicitante_email": self.usuario.email,
            "estado": Ticket.Estado.RESUELTO,
            "tecnico_asignado": self.tecnico,
        }
        datos.update(extra)
        return Ticket.objects.create(**datos)

    def resuelto(self, **extra):
        t = self.ticket(**extra)
        t.fecha_resolucion = t.fecha_creacion
        t.save(update_fields=["fecha_resolucion"])
        return t

    def url(self, ticket):
        return reverse("tickets:mi_ticket", args=[ticket.pk])

    def voto(self, ticket, valor="1", **extra):
        self.client.force_login(self.usuario)
        return self.client.post(
            reverse("tickets:calificar_tecnico", args=[self.tecnico.pk]),
            {"valor": valor, "ticket": ticket.pk, **extra},
        )

    # ---------- La lista de técnicos ----------

    def test_la_lista_de_tecnicos_aparece_bajo_propiedades(self):
        ticket = self.resuelto()
        self.client.force_login(self.usuario)
        html = self.client.get(self.url(ticket)).content.decode()

        self.assertIn('tec-lista es-directa', html)
        self.assertIn('class="tec-card"', html)
        self.assertIn(f'data-ticket="{ticket.pk}"', html)
        # Va después del bloque de propiedades, sin modal de por medio.
        self.assertLess(html.index("dash-properties"), html.index("tec-lista es-directa"))
        self.assertNotIn('data-open-modal="#modalTecnicos"', html)
        # Cada fila lleva la foto de perfil del técnico.
        self.assertIn('tec-avatar', html)

    def test_la_pagina_trae_el_token_csrf_para_que_el_voto_pase(self):
        """Sin este meta el POST del pulgar sale con 403 y no pasa nada."""
        ticket = self.resuelto()
        self.client.force_login(self.usuario)
        html = self.client.get(self.url(ticket)).content.decode()

        self.assertIn('name="csrfmiddlewaretoken" content="', html)

    def test_la_lista_limita_la_altura_si_hay_mas_de_tres_tecnicos(self):
        """Con 4 o mas técnicos la lista no crece: sale con scroll."""
        get_user_model().objects.create_user(
            "cuarto@dogger.com.co", "Cuarto", "dogger1234", rol="tecnico",
        )
        get_user_model().objects.create_user(
            "quinto@dogger.com.co", "Quinto", "dogger1234", rol="tecnico",
        )
        ticket = self.resuelto()
        self.client.force_login(self.usuario)
        html = self.client.get(self.url(ticket)).content.decode()

        self.assertIn("es-directa tiene-scroll", html)
        self.assertIn("Desliza para ver los", html)

    def test_la_lista_no_agrega_scroll_con_pocos_tecnicos(self):
        ticket = self.resuelto()
        self.client.force_login(self.usuario)
        html = self.client.get(self.url(ticket)).content.decode()

        self.assertNotIn("tiene-scroll", html)

    def test_la_lista_tambien_aparece_si_el_ticket_sigue_abierto(self):
        """Mientras el técnico trabaja ya se puede calificar el ticket."""
        ticket = self.ticket(estado=Ticket.Estado.ABIERTO, tecnico_asignado=self.tecnico)
        self.client.force_login(self.usuario)
        html = self.client.get(self.url(ticket)).content.decode()

        self.assertIn('tec-lista es-directa', html)
        self.assertIn(f'data-ticket="{ticket.pk}"', html)

    def test_la_lista_no_aparece_si_no_hay_tecnico_asignado(self):
        ticket = self.resuelto(tecnico_asignado=None)
        self.client.force_login(self.usuario)
        html = self.client.get(self.url(ticket)).content.decode()
        self.assertNotIn("tec-lista", html)

    def test_el_observador_no_llega_a_la_calificacion(self):
        """El observador no tiene Mi panel, y tampoco puede calificar por URL."""
        ticket = self.resuelto()
        self.client.force_login(self.observador)
        html = self.client.get(self.url(ticket)).content.decode()
        self.assertEqual(self.client.get(self.url(ticket)).status_code, 403)
        self.assertNotIn("tec-lista", html)

    def test_el_tecnico_no_califica_a_su_propio_detalle(self):
        ticket = self.resuelto(solicitante_email=self.tecnico.email)
        self.client.force_login(self.tecnico)
        html = self.client.get(self.url(ticket)).content.decode()
        self.assertNotIn("tec-lista", html)

    # ---------- La barra de me gusta ----------

    def test_la_barra_cuenta_lo_votado_en_tickets_resueltos(self):
        primero = self.resuelto()
        segundo = self.resuelto()
        CalificacionTecnico.registrar(self.tecnico, self.usuario, 1, ticket=primero)
        CalificacionTecnico.registrar(self.tecnico, self.otro, 1, ticket=primero)
        CalificacionTecnico.registrar(self.tecnico, self.otro, -1, ticket=segundo)

        barra = CalificacionTecnico.aprobacion_por_resueltos(self.tecnico)
        self.assertEqual(barra["total"], 3)
        self.assertEqual(barra["me_gusta"], 2)
        self.assertEqual(barra["porcentaje"], 67)

    def test_la_barra_no_mezcla_el_voto_general_al_tecnico(self):
        """El voto al técnico en general no mueve la barra de tickets resueltos."""
        ticket = self.resuelto()
        CalificacionTecnico.registrar(self.tecnico, self.usuario, -1)
        self.assertEqual(CalificacionTecnico.aprobacion_por_resueltos(self.tecnico)["total"], 0)
        self.assertEqual(self.tarjeta(ticket)["barra"]["total"], 0)
        # El voto general sí sigue visible en su propio contador.
        self.assertEqual(self.tarjeta(ticket)["no_me_gusta"], 1)

    def test_un_ticket_sin_resolver_no_entra_en_la_barra(self):
        abierto = self.ticket(estado=Ticket.Estado.ABIERTO)
        CalificacionTecnico.registrar(self.tecnico, self.usuario, 1, ticket=abierto)
        self.assertEqual(CalificacionTecnico.aprobacion_por_resueltos(self.tecnico)["total"], 0)

    def tarjeta(self, ticket):
        """La tarjeta tal como la recibe la plantilla, sin pedir la página."""
        return mapeo_de_una_tecnica(self.usuario, ticket)

    # ---------- Votar ----------

    def test_el_voto_desde_el_detalle_queda_atado_al_ticket(self):
        ticket = self.resuelto()
        respuesta = self.voto(ticket)
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertTrue(datos["ok"])
        self.assertEqual(datos["mi_voto"], 1)
        self.assertEqual(datos["me_gusta"], 1)

        voto = CalificacionTecnico.objects.get()
        self.assertEqual(voto.ticket_id, ticket.pk)
        self.assertEqual(voto.valor, CalificacionTecnico.Valor.ME_GUSTA)

    def test_votar_el_ticket_no_toca_el_voto_general(self):
        ticket = self.resuelto()
        self.client.force_login(self.usuario)
        self.client.post(reverse("tickets:calificar_tecnico", args=[self.tecnico.pk]), {"valor": "1"})
        self.voto(ticket, "-1")

        self.assertEqual(CalificacionTecnico.objects.filter(ticket__isnull=True).count(), 1)
        self.assertEqual(
            CalificacionTecnico.conteos(self.tecnico, self.usuario)["mi_voto"], 1
        )
        self.assertEqual(
            CalificacionTecnico.conteos(self.tecnico, self.usuario, ticket)["mi_voto"], -1
        )

    def test_votar_el_mismo_ticket_dos_veces_quita_el_voto(self):
        ticket = self.resuelto()
        self.voto(ticket)
        self.voto(ticket)
        self.assertEqual(CalificacionTecnico.objects.filter(ticket=ticket).count(), 0)

    def test_una_persona_puede_votar_en_dos_tickets_distintos(self):
        uno, otro = self.resuelto(), self.resuelto()
        self.voto(uno)
        self.voto(otro)
        self.assertEqual(CalificacionTecnico.objects.filter(usuario=self.usuario).count(), 2)

    def test_no_se_puede_votar_el_ticket_de_otra_persona(self):
        ticket = self.resuelto()
        self.client.force_login(self.otro)
        respuesta = self.client.post(
            reverse("tickets:calificar_tecnico", args=[self.tecnico.pk]),
            {"valor": "1", "ticket": ticket.pk},
        )
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(CalificacionTecnico.objects.count(), 0)

    def test_no_se_puede_votar_un_ticket_sin_tecnico_asignado(self):
        ticket = self.ticket(estado=Ticket.Estado.EN_PROGRESO, tecnico_asignado=None)
        respuesta = self.voto(ticket)
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(CalificacionTecnico.objects.count(), 0)

    def test_se_puede_votar_un_ticket_que_sigue_abierto(self):
        ticket = self.ticket(estado=Ticket.Estado.ABIERTO, tecnico_asignado=self.tecnico)
        respuesta = self.voto(ticket)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(CalificacionTecnico.objects.get().ticket_id, ticket.pk)

    def test_el_observador_no_puede_votar_aunque_conozca_la_ruta(self):
        ticket = self.resuelto()
        self.client.force_login(self.observador)
        respuesta = self.client.post(
            reverse("tickets:calificar_tecnico", args=[self.tecnico.pk]),
            {"valor": "1", "ticket": ticket.pk},
        )
        self.assertEqual(respuesta.status_code, 403)

    # ---------- El modal ----------

    def test_el_modal_muestra_los_tecnicos_activos_con_su_barra(self):
        ticket = self.resuelto()
        CalificacionTecnico.registrar(self.tecnico, self.usuario, 1, ticket=ticket)
        self.client.force_login(self.usuario)
        html = self.client.get(self.url(ticket)).content.decode()
        self.assertIn(self.tecnico.nombre, html)
        self.assertIn(self.ayudante.nombre, html)
        self.assertIn("tec-barra", html)
        self.assertIn("100% de aprobación", html)

    def test_sin_votos_la_barra_dice_que_no_hay(self):
        ticket = self.resuelto()
        self.client.force_login(self.usuario)
        html = self.client.get(self.url(ticket)).content.decode()
        self.assertIn("Todavía sin votos en tickets resueltos.", html)


class BackfillDeVotosViejos(TestCase):
    """Los votos que ya existían se atan a su ticket cuando no hay duda.

    Antes el voto era solo "al técnico"; ahora puede ser de un ticket. Si la
    persona tenía un único ticket resuelto de ese técnico, ese era el trabajo
    que estaba calificando. Con varios, no se puede saber cuál y se deja como
    voto general: inventar uno sería peor que dejarlo.
    """

    @classmethod
    def setUpTestData(cls):
        cls.persona = get_user_model().objects.create_user(
            "persona@dogger.com.co", "Persona", "dogger1234", rol="usuario",
        )
        cls.tec = get_user_model().objects.create_user(
            "tec@dogger.com.co", "Tecnico", "dogger1234", rol="tecnico",
        )

    def ticket(self):
        t = Ticket.objects.create(
            titulo="Algo",
            solicitante_email=self.persona.email,
            estado=Ticket.Estado.RESUELTO,
            tecnico_asignado=self.tec,
        )
        t.fecha_resolucion = t.fecha_creacion
        t.save(update_fields=["fecha_resolucion"])
        return t

    def atar(self):
        """Corre el paso de la migración que ata los votos viejos.

        Se le pasa el registro de apps de verdad (no el histórico, que en este
        punto todavía no tiene el campo ticket) y la conexión, que es lo único
        que el paso necesita: pregunta por la columna antes de hacer nada. En un
        test no se puede abrir el editor de esquema, porque SQLite no admite
        cambiar el esquema dentro de una transacción.
        """
        from importlib import import_module
        from types import SimpleNamespace

        from django.apps import apps as apps_registro
        from django.db import connection

        modulo = import_module("apps.tickets.migrations.0017_calificacion_tecnico_por_ticket")
        return modulo.atar_votos_existentes(apps_registro, SimpleNamespace(connection=connection))

    def test_un_voto_se_ata_a_su_unico_ticket_resuelto(self):
        ticket = self.ticket()
        voto = CalificacionTecnico.registrar(self.tec, self.persona, 1)

        self.assertEqual(voto, 1)
        self.atar()

        voto = CalificacionTecnico.objects.get()
        self.assertEqual(voto.ticket_id, ticket.pk)

    def test_con_dos_tickets_el_voto_se_queda_general(self):
        self.ticket()
        self.ticket()
        CalificacionTecnico.registrar(self.tec, self.persona, 1)

        self.atar()

        self.assertIsNone(CalificacionTecnico.objects.get().ticket_id)

    def test_sin_ticket_resuelto_el_voto_se_queda_general(self):
        CalificacionTecnico.registrar(self.tec, self.persona, 1)
        self.atar()
        self.assertIsNone(CalificacionTecnico.objects.get().ticket_id)


def mapeo_de_una_tecnica(usuario, ticket):
    """El mapeo que la vista pasa a la plantilla, para un técnico concreto."""
    from apps.tickets.services.tecnicos import mapeados_del_tecnico

    for tecnico in mapeados_del_tecnico(usuario, ticket):
        if tecnico["pk"] == ticket.tecnico_asignado_id:
            return tecnico
    raise AssertionError("el técnico del ticket no está en la lista")
