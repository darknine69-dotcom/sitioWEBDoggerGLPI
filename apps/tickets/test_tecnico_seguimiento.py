"""Prueba lo nuevo del rol de técnico: monitoreo, historial y papelera.

Son tres piezas que el técnico no tenía:

  · **Papelera**: el administrador ya podía recuperar un ticket borrado; el
    técnico, que es quien a veces borra o quien hereda el caso, no. Ahora
    comparte la misma vista y las mismas funciones.
  · **Historial**: lo que él dejó hecho — cada respuesta que escribió en un
    hilo y cada ticket que resolvió — en una sola tabla ordenada.
  · **Monitoreo**: la presión de sus supervisores y el recuento de sus
    tickets por vencer, con el mismo diseño del panel del observador.
"""

from datetime import timedelta

from django.core import mail
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Usuario
from apps.tickets.models import Categoria, ElementoMiLista, Punto, Ticket, TicketComentario, ZonaObservador

HORAS_MEDIA = 12  # prioridad media: 12 h de ANS


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class BaseTecnicoTest(TestCase):
    def setUp(self):
        self.tecnico = Usuario.objects.create_user(
            email="tec@x.com", password="x", nombre="Técnico Uno",
            rol=Usuario.Rol.TECNICO,
        )
        self.observador = Usuario.objects.create_user(
            email="obs@x.com", password="x", nombre="Obs",
            rol=Usuario.Rol.OBSERVADOR,
        )
        self.solicitante = Usuario.objects.create_user(
            email="ana@x.com", password="x", nombre="Ana",
            rol=Usuario.Rol.USUARIO,
        )
        mail.outbox.clear()
        self.client.force_login(self.tecnico)

    def _ticket(self, tecnico=None, horas=None, prioridad=Ticket.Prioridad.MEDIA,
                estado=Ticket.Estado.ABIERTO, codigo="HD-0001",
                titulo="Impresora del mostrador sin papel"):
        ticket = Ticket.objects.create(
            titulo=titulo,
            descripcion="No saca nada.",
            prioridad=prioridad,
            estado=estado,
            solicitante_nombre="Ana",
            solicitante_email="ana@x.com",
            solicitante_punto="Punto 1",
            tecnico_asignado=tecnico if tecnico is not None else self.tecnico,
            codigo=codigo,
        )
        if horas is not None:
            Ticket.objects.filter(pk=ticket.pk).update(
                fecha_creacion=timezone.now() - timedelta(hours=horas)
            )
            ticket.refresh_from_db()
        mail.outbox.clear()
        return ticket

    def _responder(self, ticket, texto="Ya reviso el equipo.", tecnico=None,
                   es_interno=False):
        """El técnico escribe en el hilo. Escribe sin notificar: aquí no se
        prueba el aviso al solicitante, sino el registro del historial."""
        mail.outbox.clear()
        autor = tecnico if tecnico is not None else self.tecnico
        comentario = TicketComentario.objects.create(
            ticket=ticket,
            usuario=autor,
            autor_nombre=autor.nombre,
            comentario=texto,
            es_interno=es_interno,
        )
        mail.outbox.clear()
        return comentario

    def _presionar(self, ticket, texto="¿Puedes cerrarlo hoy?",
                   quien=None):
        """El botón de «presionar al técnico» visto desde el punto de venta."""
        mail.outbox.clear()
        quien = quien or self.solicitante
        return TicketComentario.objects.create(
            ticket=ticket,
            usuario=quien,
            autor_nombre=quien.nombre,
            comentario=texto,
            es_interno=False,
            es_presion=True,
        )


# =====================================================================
# Menú
# =====================================================================
class MenuTecnicoTest(BaseTecnicoTest):
    def test_el_tecnico_ve_las_tres_secciones_en_el_menu(self):
        html = self.client.get(reverse("tickets:tec_monitoreo")).content.decode()
        self.assertIn(reverse("tickets:tec_monitoreo"), html)
        self.assertIn(reverse("tickets:tec_historial"), html)
        self.assertIn(reverse("tickets:papelera"), html)
        self.assertIn(reverse("tickets:categorias_arbol"), html)
        self.assertIn("Seguimiento", html)

    def test_el_punto_de_venta_no_ve_esas_secciones(self):
        self.client.force_login(self.solicitante)
        html = self.client.get(reverse("tickets:mi_panel")).content.decode()
        self.assertNotIn(reverse("tickets:tec_historial"), html)
        self.assertNotIn(reverse("tickets:tec_monitoreo"), html)
        self.assertIn(reverse("tickets:categorias_publico"), html)

    def test_el_observador_no_ve_esas_secciones(self):
        self.client.force_login(self.observador)
        html = self.client.get(reverse("tickets:obs_monitoreo")).content.decode()
        self.assertNotIn(reverse("tickets:tec_historial"), html)
        self.assertNotIn(reverse("tickets:tec_monitoreo"), html)
        self.assertIn(reverse("tickets:categorias_publico"), html)

    def test_el_tecnico_puede_crear_y_editar_categorias(self):
        pantalla = self.client.get(reverse("tickets:categorias_arbol"))
        self.assertEqual(pantalla.status_code, 200)
        self.assertContains(pantalla, "Crear categoría")

        creada = self.client.post(
            reverse("tickets:categoria_grupo_crear"),
            {"nombre": "Categoría del técnico"},
        )
        self.assertEqual(creada.status_code, 302)
        pantalla = self.client.get(reverse("tickets:categorias_arbol"))
        self.assertContains(pantalla, "Categoría del técnico")
        self.assertContains(pantalla, "Nueva subcategoría")

        creada = self.client.post(
            reverse("tickets:categoria_crear"),
            {
                "grupo": "Categoría del técnico",
                "nombre": "Subcategoría del técnico",
                "descripcion": "Detalle creado por técnico.",
                "prioridad_default": "media",
                "ans_horas": 12,
                "glpi_category_id": "",
                "tecnico_default": "",
            },
        )
        self.assertEqual(creada.status_code, 302)
        categoria = Categoria.objects.get(nombre="Subcategoría del técnico")
        editada = self.client.post(
            reverse("tickets:categoria_actualizar", args=[categoria.pk]),
            {
                "grupo": categoria.grupo,
                "nombre": categoria.nombre,
                "descripcion": "Detalle editado por técnico.",
                "prioridad_default": "alta",
                "ans_horas": 8,
                "glpi_category_id": "",
                "tecnico_default": "",
            },
        )
        self.assertEqual(editada.status_code, 302)
        categoria.refresh_from_db()
        self.assertEqual(categoria.descripcion, "Detalle editado por técnico.")
        self.assertEqual(categoria.prioridad_default, "alta")

    def test_el_enlace_publico_de_categorias_lleva_al_tecnico_a_gestion(self):
        respuesta = self.client.get(reverse("tickets:categorias_publico"))
        self.assertRedirects(respuesta, reverse("tickets:categorias_arbol"))

    def test_el_tecnico_no_puede_desactivar_ni_eliminar_categorias(self):
        categoria = Categoria.objects.create(
            grupo="Protección",
            nombre="Protección de prueba",
        )
        self.client.raise_request_exception = False

        self.assertEqual(
            self.client.post(
                reverse("tickets:categoria_toggle", args=[categoria.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("tickets:categoria_eliminar", args=[categoria.pk])
            ).status_code,
            403,
        )

    def test_observador_consulta_categorias_sin_accion_para_crear_ticket(self):
        self.client.force_login(self.observador)
        respuesta = self.client.get(reverse("tickets:categorias_publico"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Crear solicitud aquí")


# =====================================================================
# Papelera
# =====================================================================
class PapeleraTecnicoTest(BaseTecnicoTest):
    def test_el_tecnico_entra_a_la_papelera(self):
        respuesta = self.client.get(reverse("tickets:papelera"))
        self.assertEqual(respuesta.status_code, 200)

    def test_el_punto_de_venta_no_entra(self):
        self.client.force_login(self.solicitante)
        self.client.raise_request_exception = False
        self.assertEqual(
            self.client.get(reverse("tickets:papelera")).status_code, 403
        )

    def test_el_papelera_muestra_lo_que_el_tecnico_borro(self):
        ticket = self._ticket()
        self.client.post(reverse("tickets:eliminar", args=[ticket.pk]))
        html = self.client.get(reverse("tickets:papelera")).content.decode()
        self.assertIn("HD-0001", html)

    def test_el_tecnico_restaura_un_ticket(self):
        ticket = self._ticket()
        self.client.post(reverse("tickets:eliminar", args=[ticket.pk]))
        self.assertFalse(Ticket.objects.filter(pk=ticket.pk).exists())

        self.client.post(reverse("tickets:restaurar", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertTrue(Ticket.objects.filter(pk=ticket.pk).exists())
        self.assertFalse(ticket.en_la_papelera)

    def test_el_tecnico_purga_un_ticket(self):
        ticket = self._ticket()
        self.client.post(reverse("tickets:eliminar", args=[ticket.pk]))
        self.client.post(reverse("tickets:purgar", args=[ticket.pk]))
        self.assertFalse(Ticket.con_eliminados.filter(pk=ticket.pk).exists())

    def test_el_ticket_borrado_deja_de_salir_en_su_panel(self):
        ticket = self._ticket()
        self.client.post(reverse("tickets:eliminar", args=[ticket.pk]))
        # El aviso de «enviado a la papelera» lleva el código y se pinta en
        # la próxima página; se consume aquí para que no ensucie la mirada.
        self.client.get(reverse("tickets:papelera"))
        self.client.force_login(self.tecnico)
        contexto = self.client.get(reverse("tickets:tec_historial")).context
        self.assertEqual(contexto["total"], 0)
        self.assertEqual(contexto["resueltos_total"], 0)


# =====================================================================
# Historial
# =====================================================================
class HistorialTecnicoTest(BaseTecnicoTest):
    def test_historial_enriquece_respuestas_y_cierres_con_ficha_de_trazabilidad(self):
        ticket = self._ticket(codigo="HD-0102", prioridad=Ticket.Prioridad.ALTA)
        ticket.fecha_creacion = timezone.now() - timedelta(hours=3)
        ticket.save(update_fields=["fecha_creacion"])
        comentario = self._responder(ticket, texto="Se actualizó el sistema.")

        ticket.estado = Ticket.Estado.RESUELTO
        ticket.fecha_resolucion = timezone.now()
        ticket.fecha_cierre = ticket.fecha_resolucion
        ticket.save(update_fields=["estado", "fecha_resolucion", "fecha_cierre"])

        respuesta = self.client.get(
            reverse("tickets:tec_historial"), {"tipo": "respuestas"}
        )
        entrada_respuesta = respuesta.context["entradas"][0]
        self.assertEqual(entrada_respuesta["registro_id"], f"COM-{comentario.pk:06d}")
        self.assertEqual(entrada_respuesta["accion"], "Respuesta")
        self.assertEqual(entrada_respuesta["solicitante"], "Ana")
        self.assertEqual(entrada_respuesta["tecnico"], "Técnico Uno")
        self.assertEqual(entrada_respuesta["estado_actual"], "Resuelto")
        self.assertIn("3h", entrada_respuesta["tiempo_respuesta"])
        self.assertEqual(entrada_respuesta["version_sistema"], "No registrada en el ticket")
        self.assertContains(respuesta, "Fecha y hora")
        self.assertContains(respuesta, "Supervisor responsable")
        self.assertContains(respuesta, "Tiempo total de resolución")
        self.assertContains(respuesta, "Comentarios adicionales")
        self.assertContains(respuesta, "Usuario solicitante")
        self.assertContains(respuesta, "Técnico asignado")
        self.assertContains(respuesta, "Prioridad / SLA")
        self.assertContains(respuesta, "Versión del sistema")
        self.assertNotContains(respuesta, "Ver ficha y detalle")

        cierre = self.client.get(
            reverse("tickets:tec_historial"), {"tipo": "resueltos"}
        )
        entrada_cierre = cierre.context["entradas"][0]
        self.assertEqual(entrada_cierre["registro_id"], f"RES-{ticket.pk:06d}")
        self.assertEqual(entrada_cierre["accion"], "Cierre / resolución")
        self.assertIn("3h", entrada_cierre["tiempo_resolucion"])

    def test_ve_los_tickets_que_resolvio(self):
        self._ticket(codigo="HD-0100", estado=Ticket.Estado.RESUELTO)
        html = self.client.get(reverse("tickets:tec_historial")).content.decode()
        self.assertIn("HD-0100", html)
        self.assertIn("Resuelto", html)

    def test_ve_las_respuestas_que_escribio(self):
        ticket = self._ticket(codigo="HD-0101")
        self._responder(ticket, texto="Cambié el rodillo, ya imprime.")
        html = self.client.get(reverse("tickets:tec_historial")).content.decode()
        self.assertIn("HD-0101", html)
        self.assertIn("Cambié el rodillo, ya imprime.", html)
        self.assertIn("Respuesta", html)

    def test_el_historial_une_respuestas_y_resueltos_en_una_sola_tabla(self):
        self._ticket(codigo="HD-0200", estado=Ticket.Estado.RESUELTO)
        self._responder(self._ticket(codigo="HD-0201"), "Listo.")
        respuesta = self.client.get(reverse("tickets:tec_historial"))
        html = respuesta.content.decode()
        self.assertIn("HD-0200", html)
        self.assertIn("HD-0201", html)
        self.assertEqual(html.count("<table"), 1)

    def test_el_mas_reciente_sale_primero(self):
        viejo = self._ticket(codigo="HD-0300", estado=Ticket.Estado.RESUELTO)
        Ticket.objects.filter(pk=viejo.pk).update(
            fecha_resolucion=timezone.now() - timedelta(days=30)
        )
        self._ticket(codigo="HD-0301", estado=Ticket.Estado.RESUELTO)
        html = self.client.get(reverse("tickets:tec_historial")).content.decode()
        self.assertLess(html.index("HD-0301"), html.index("HD-0300"))

    def test_el_filtro_por_tipo_separa_las_dos_fuentes(self):
        self._ticket(codigo="HD-0400", estado=Ticket.Estado.RESUELTO)
        self._responder(self._ticket(codigo="HD-0401"), "Listo.")

        html = self.client.get(
            reverse("tickets:tec_historial"), {"tipo": "resueltos"}
        ).content.decode()
        self.assertIn("HD-0400", html)
        self.assertNotIn("HD-0401", html)

        html = self.client.get(
            reverse("tickets:tec_historial"), {"tipo": "respuestas"}
        ).content.decode()
        self.assertIn("HD-0401", html)
        self.assertNotIn("HD-0400", html)

    def test_busca_por_codigo_y_por_titulo(self):
        self._ticket(codigo="HD-0500", titulo="Router de contabilidad caído",
                     estado=Ticket.Estado.RESUELTO)
        self._ticket(codigo="HD-0501", titulo="Monitor parpadea",
                     estado=Ticket.Estado.RESUELTO)

        html = self.client.get(
            reverse("tickets:tec_historial"), {"q": "router"}
        ).content.decode()
        self.assertIn("HD-0500", html)
        self.assertNotIn("HD-0501", html)

    def test_no_mezcla_lo_de_los_demas_tecnicos(self):
        otro = Usuario.objects.create_user(
            email="otro@x.com", password="x", nombre="Técnico Dos",
            rol=Usuario.Rol.TECNICO,
        )
        self._ticket(codigo="HD-0600", tecnico=otro, estado=Ticket.Estado.RESUELTO)
        self._responder(
            self._ticket(codigo="HD-0601", tecnico=otro),
            "De mi otro.",
            tecnico=otro,
        )

        html = self.client.get(reverse("tickets:tec_historial")).content.decode()
        self.assertNotIn("HD-0600", html)
        self.assertNotIn("HD-0601", html)

    def test_el_filtro_de_busqueda_alcanza_a_los_mensajes(self):
        """Buscar no solo mira el título: también el texto del mensaje."""
        ticket = self._ticket(codigo="HD-0700")
        self._responder(ticket, "Reemplacé la fuente de alimentación.")
        html = self.client.get(
            reverse("tickets:tec_historial"), {"q": "HD-0700"}
        ).content.decode()
        self.assertIn("Reemplacé la fuente de alimentación.", html)

    def test_las_respuestas_internas_tambien_cuentan(self):
        """Son suyas: las escribió él, aunque solo las vea el staff."""
        ticket = self._ticket(codigo="HD-0800")
        self._responder(ticket, "Nota interna para el equipo.", es_interno=True)
        html = self.client.get(reverse("tickets:tec_historial")).content.decode()
        self.assertIn("HD-0800", html)
        self.assertIn("Nota interna para el equipo.", html)

    def test_pagina_cuando_hay_mas_de_lo_que_cabe(self):
        for i in range(12):
            self._ticket(codigo=f"HD-09{i:02d}", estado=Ticket.Estado.RESUELTO)
        respuesta = self.client.get(
            reverse("tickets:tec_historial"), {"per_page": "5"}
        )
        contexto = respuesta.context
        self.assertEqual(contexto["pagina"], 1)
        self.assertEqual(contexto["num_paginas"], 3)
        self.assertTrue(contexto["tiene_siguiente"])
        self.assertFalse(contexto["tiene_anterior"])
        self.assertEqual(len(contexto["entradas"]), 5)
        html = respuesta.content.decode()
        self.assertIn("Siguiente", html)
        self.assertIn("Anterior", html)
        self.assertIn("Página 1 de 3", html)

    def test_las_paginas_no_se_repiten_ni_dejan_nada_fuera(self):
        """La mezcla de las dos fuentes se hace en Python, así que una
        entrada no puede salir dos veces ni quedarse sin página."""
        for i in range(6):
            self._ticket(codigo=f"HD-12{i:02d}", estado=Ticket.Estado.RESUELTO)
            self._responder(self._ticket(codigo=f"HD-13{i:02d}"), f"R{i}")

        vistos = []
        for p in range(1, 4):
            respuesta = self.client.get(
                reverse("tickets:tec_historial"),
                {"per_page": "5", "page": str(p)},
            )
            self.assertEqual(respuesta.status_code, 200)
            vistos += [e["codigo"] for e in respuesta.context["entradas"]]

        self.assertEqual(len(vistos), 12)
        self.assertEqual(len(set(vistos)), 12)

    def test_los_siguientes_son_todos_los_anteriores(self):
        """Cada página sigue a la anterior sin saltos: se recorre la línea
        entera y sale en orden descendente."""
        for i in range(4):
            self._ticket(codigo=f"HD-14{i:02d}", estado=Ticket.Estado.RESUELTO)
        fechas = []
        for p in (1, 2):
            respuesta = self.client.get(
                reverse("tickets:tec_historial"), {"per_page": "3", "page": str(p)}
            )
            fechas += [e["fecha"] for e in respuesta.context["entradas"]]
        self.assertEqual(len(fechas), 4)
        self.assertEqual(fechas, sorted(fechas, reverse=True))

    def test_la_ultima_pagina_no_se_queda_corta(self):
        for i in range(7):
            self._ticket(codigo=f"HD-15{i:02d}", estado=Ticket.Estado.RESUELTO)
        respuesta = self.client.get(
            reverse("tickets:tec_historial"), {"per_page": "5"}
        )
        self.assertEqual(respuesta.context["num_paginas"], 2)
        ultima = self.client.get(
            reverse("tickets:tec_historial"), {"per_page": "5", "page": "2"}
        )
        self.assertEqual(len(ultima.context["entradas"]), 2)
        self.assertFalse(ultima.context["tiene_siguiente"])

    def test_una_pagina_que_no_existe_se_vuelve_a_la_ultima(self):
        self._ticket(codigo="HD-1600", estado=Ticket.Estado.RESUELTO)
        respuesta = self.client.get(
            reverse("tickets:tec_historial"), {"page": "99"}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["pagina"], 1)
        self.assertEqual(len(respuesta.context["entradas"]), 1)

    def test_los_indicadores_reflejan_las_dos_fuentes(self):
        self._ticket(codigo="HD-1000", estado=Ticket.Estado.RESUELTO)
        self._responder(self._ticket(codigo="HD-1001"), "Uno.")
        self._responder(self._ticket(codigo="HD-1002"), "Dos.")
        contexto = self.client.get(reverse("tickets:tec_historial")).context
        self.assertEqual(contexto["respuestas_total"], 2)
        self.assertEqual(contexto["resueltos_total"], 1)
        self.assertEqual(contexto["total"], 3)

    def test_no_pasa_un_union_por_la_base(self):
        """Guarda contra la caída original de la página.

        SQL Server no deja `ORDER BY` dentro de una subconsulta sin `TOP` u
        `OFFSET`, y para contar las filas de un `union` Django arma
        exactamente eso (error 42000, 1033). La mezcla se hace en Python, así
        que aquí no puede aparecer ningún `UNION` en el SQL.
        """
        self._ticket(codigo="HD-1700", estado=Ticket.Estado.RESUELTO)
        self._responder(self._ticket(codigo="HD-1701"), "Una respuesta.")

        with CaptureQueriesContext(connection) as capturadas:
            self.client.get(reverse("tickets:tec_historial")).content

        con_union = [
            q["sql"] for q in capturadas.captured_queries
            if "UNION" in q["sql"].upper()
        ]
        self.assertEqual(con_union, [], "La vista emitió una consulta con UNION")
        # Y sí tienen que salir consultas: si no, la prueba no prueba nada.
        self.assertTrue(capturadas.captured_queries)

    def test_el_punto_de_venta_no_entra_al_historial(self):
        self.client.force_login(self.solicitante)
        self.client.raise_request_exception = False
        self.assertEqual(
            self.client.get(reverse("tickets:tec_historial")).status_code, 403
        )


# =====================================================================
# Monitoreo
# =====================================================================
class MonitoreoTecnicoTest(BaseTecnicoTest):
    def test_muestra_resumen_visual_priorizando_alertas_ans(self):
        self._ticket(codigo="HD-1998", horas=20)
        self._ticket(codigo="HD-1999", horas=10)

        respuesta = self.client.get(reverse("tickets:tec_monitoreo"))
        html = respuesta.content.decode()

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Resumen de atención")
        self.assertContains(respuesta, "Atención prioritaria")
        self.assertContains(respuesta, "1 ticket con el ANS vencido")
        self.assertContains(respuesta, "is-vencido")
        self.assertContains(respuesta, "tec-monitor-section")
        self.assertContains(respuesta, "tec-monitor-overview")

    def test_cuenta_los_tickets_por_vencer(self):
        self._ticket(codigo="HD-2000", horas=10)   # dentro del aviso
        self._ticket(codigo="HD-2001", horas=20)   # ya se pasó
        self._ticket(codigo="HD-2002", horas=1)    # todavía tiene tiempo

        contexto = self.client.get(reverse("tickets:tec_monitoreo")).context
        self.assertEqual(contexto["total_por_vencer"], 1)
        self.assertEqual(contexto["total_vencidos"], 1)
        self.assertEqual(len(contexto["por_vencer"]), 2)

    def test_cada_ficha_lleva_el_cronometro_corriendo(self):
        self._ticket(codigo="HD-2100", horas=13)
        html = self.client.get(reverse("tickets:tec_monitoreo")).content.decode()
        self.assertIn('data-ans-codigo="HD-2100"', html)
        self.assertIn('data-ans-limit', html)
        self.assertIn('class="ans-ficha', html)

    def test_la_ventana_explicativa_tambien_esta_aqui(self):
        self._ticket(codigo="HD-2150", horas=13)
        html = self.client.get(reverse("tickets:tec_monitoreo")).content.decode()
        self.assertIn('id="ansModal"', html)

    def test_el_ticket_que_no_va_justo_no_sale(self):
        """El que aún tiene tiempo no entra en la sección del ANS.

        Sí puede aparecer en «Tus tickets», que lista todo lo suyo, pero en
        «Por vencer» no: ahí solo caben los que ya están en el aviso o se
        pasaron.
        """
        self._ticket(codigo="HD-2200", horas=1)
        contexto = self.client.get(reverse("tickets:tec_monitoreo")).context
        self.assertNotIn("HD-2200", [t.codigo for t in contexto["por_vencer"]])

        html = self.client.get(reverse("tickets:tec_monitoreo")).content.decode()
        seccion = html.split('id="por-vencer"')[1].split("</section>")[0]
        self.assertNotIn("HD-2200", seccion)

    def test_los_tickets_resueltos_no_entran(self):
        """Un ticket resuelto ya no tiene ANS que vigilar."""
        self._ticket(codigo="HD-2300", horas=20, estado=Ticket.Estado.RESUELTO)
        contexto = self.client.get(reverse("tickets:tec_monitoreo")).context
        self.assertEqual(len(contexto["por_vencer"]), 0)

    def test_la_tabla_de_tickets_es_el_destino_de_los_indicadores(self):
        """Los de «Asignados», «Abiertos» y «Resueltos hoy» bajan a la
        tabla y le dejan puesto el filtro que dicen."""
        self._ticket(codigo="HD-2500")
        self._ticket(codigo="HD-2501", estado=Ticket.Estado.RESUELTO)

        html = self.client.get(reverse("tickets:tec_monitoreo")).content.decode()
        self.assertIn('id="f-asignados"', html)
        self.assertIn('id="f-abiertos"', html)
        self.assertIn('id="f-resueltos-hoy"', html)
        self.assertIn('id="tabla-tec"', html)
        # Filas marcadas para que el filtro sepa qué es abierto y qué hoy.
        self.assertIn('data-grupo="abierto"', html)
        self.assertIn('data-grupo="cerrado"', html)
        self.assertIn('data-hoy="1"', html)

    # ---------------------------------------------------------------
    # Desde qué zona lo miran
    # ---------------------------------------------------------------
    def test_dice_desde_que_zona_lo_presionan(self):
        """Quien presiona es el observador de una zona: la tarjeta del
        mensaje y el resumen de arriba llevan su nombre."""
        ZonaObservador.objects.create(observador=self.observador, nombre="Norte")
        ticket = self._ticket(codigo="HD-2600")
        self._presionar(ticket, texto="¿Ya fuiste?", quien=self.observador)

        contexto = self.client.get(reverse("tickets:tec_monitoreo")).context
        self.assertEqual(
            [z.nombre for z in contexto["presiones"][0].zonas], ["Norte"]
        )
        self.assertEqual(
            [f["zona"].nombre for f in contexto["zonas_mirada"]], ["Norte"]
        )
        self.assertEqual(contexto["zonas_mirada"][0]["presiones"], 1)

        html = self.client.get(reverse("tickets:tec_monitoreo")).content.decode()
        self.assertIn('id="zonas-que-vigilan"', html)
        self.assertIn("Supervisa", html)
        self.assertIn("Norte", html)

    def test_el_punto_del_ticket_tambien_dice_la_zona(self):
        """El punto de venta del ticket está en una zona: desde ahí también
        se mira ese caso, aunque nadie haya presionado nada."""
        zona = ZonaObservador.objects.create(
            observador=self.observador, nombre="Sur"
        )
        punto = Punto.objects.create(nombre="Punto 1")
        ElementoMiLista.objects.create(
            observador=self.observador, tipo=ElementoMiLista.TIPO_PUNTO,
            punto=punto, zona=zona,
        )
        self._ticket(codigo="HD-2610", horas=11)

        contexto = self.client.get(reverse("tickets:tec_monitoreo")).context
        self.assertEqual(
            [z.nombre for z in contexto["por_vencer"][0].zonas], ["Sur"]
        )
        self.assertEqual(
            [f["zona"].nombre for f in contexto["zonas_mirada"]], ["Sur"]
        )

    def test_sin_zonas_la_seccion_existe_y_lo_dice(self):
        """El ancla tiene que estar aunque no haya nada que enseñar, si no
        el indicador no lleva a ninguna parte."""
        html = self.client.get(reverse("tickets:tec_monitoreo")).content.decode()
        self.assertIn('id="zonas-que-vigilan"', html)
        self.assertIn("Ninguna zona tiene hoy vista", html)

    def test_ve_la_presion_de_los_supervisores(self):
        ticket = self._ticket(codigo="HD-2400")
        self._presionar(ticket, texto="¿Puedes cerrarlo hoy?")
        contexto = self.client.get(reverse("tickets:tec_monitoreo")).context
        self.assertEqual(contexto["total_presiones"], 1)
        self.assertEqual(len(contexto["presiones"]), 1)
        html = self.client.get(reverse("tickets:tec_monitoreo")).content.decode()
        self.assertIn("¿Puedes cerrarlo hoy?", html)

    def test_el_mensaje_normal_no_es_presion(self):
        """Escribir en el hilo no es presionar: solo cuenta el botón."""
        ticket = self._ticket(codigo="HD-2500")
        self._responder(
            ticket, "Hola, ¿cómo va?", tecnico=self.solicitante
        )
        contexto = self.client.get(reverse("tickets:tec_monitoreo")).context
        self.assertEqual(contexto["total_presiones"], 0)

    def test_no_ve_la_presion_de_los_demas_tecnicos(self):
        otro = Usuario.objects.create_user(
            email="otro2@x.com", password="x", nombre="Técnico Dos",
            rol=Usuario.Rol.TECNICO,
        )
        self._presionar(self._ticket(codigo="HD-2600", tecnico=otro))
        contexto = self.client.get(reverse("tickets:tec_monitoreo")).context
        self.assertEqual(contexto["total_presiones"], 0)

    def test_la_presion_muestra_quien_y_que_ticket(self):
        ticket = self._ticket(codigo="HD-2700")
        self._presionar(ticket, texto="El cliente insiste.")
        html = self.client.get(reverse("tickets:tec_monitoreo")).content.decode()
        self.assertIn("El cliente insiste.", html)
        self.assertIn("HD-2700", html)
        self.assertIn("Ana", html)

    def test_cuenta_los_resueltos_de_hoy(self):
        self._ticket(codigo="HD-2800", estado=Ticket.Estado.RESUELTO)
        self._ticket(codigo="HD-2801")
        contexto = self.client.get(reverse("tickets:tec_monitoreo")).context
        self.assertEqual(contexto["resueltos_hoy"], 1)

    def test_el_observador_no_entra(self):
        self.client.force_login(self.observador)
        self.client.raise_request_exception = False
        self.assertEqual(
            self.client.get(reverse("tickets:tec_monitoreo")).status_code, 403
        )

    def test_el_punto_de_venta_no_entra(self):
        self.client.force_login(self.solicitante)
        self.client.raise_request_exception = False
        self.assertEqual(
            self.client.get(reverse("tickets:tec_monitoreo")).status_code, 403
        )


# =====================================================================
# Los botones dejan la marca
# =====================================================================
class MarcaDePresionTest(BaseTecnicoTest):
    def test_el_boton_del_observador_marca_el_mensaje(self):
        """El observador presiona por su botón; el mensaje queda marcado."""
        from apps.tickets.models import ElementoMiLista, ZonaObservador

        ticket = self._ticket(codigo="HD-3000")
        zona = ZonaObservador.objects.create(
            observador=self.observador, nombre="Sede norte"
        )
        ElementoMiLista.objects.create(
            observador=self.observador, usuario=self.solicitante,
            usuario_email="ana@x.com", zona=zona,
        )
        self.client.force_login(self.observador)
        mail.outbox.clear()
        self.client.post(reverse("tickets:obs_presionar", args=[ticket.pk]), {
            "mensaje": "Recuérdaselo, por favor.",
            "volver": reverse("tickets:obs_monitoreo"),
        })
        comentario = TicketComentario.objects.get(ticket=ticket)
        self.assertTrue(comentario.es_presion)

    def test_el_boton_del_punto_de_venta_marca_el_mensaje(self):
        ticket = self._ticket(codigo="HD-3001")
        self.client.force_login(self.solicitante)
        mail.outbox.clear()
        self.client.post(reverse("tickets:mi_presionar", args=[ticket.pk]), {
            "mensaje": "Necesito el equipo ya.",
        })
        comentario = TicketComentario.objects.get(ticket=ticket)
        self.assertTrue(comentario.es_presion)

    def test_una_respuesta_cualquiera_no_se_marca(self):
        """La marca la ponen solo los dos botones, nada más."""
        ticket = self._ticket(codigo="HD-3002")
        comentario = self._responder(ticket, "Todo listo.")
        self.assertFalse(comentario.es_presion)
