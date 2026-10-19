"""Sonda temporal: revisa que el panel de Mi lista lleve la ficha de cada
usuario (cifras, tickets y respuestas) en el JSON que pinta la tarjeta."""

import json

from django.test import TestCase

from apps.accounts.models import Usuario
from apps.tickets.models import (
    ElementoMiLista,
    Punto,
    Ticket,
    TicketComentario,
    ZonaObservador,
)


class SondaPanelTest(TestCase):
    def test_panel_lleva_ficha(self):
        obs = Usuario.objects.create_user(
            email="obs@dogger.com", password="x", nombre="Olga",
            rol=Usuario.Rol.OBSERVADOR)
        tec = Usuario.objects.create_user(
            email="tec@dogger.com", password="x", nombre="Tecnico Uno",
            rol=Usuario.Rol.TECNICO)
        punto = Punto.objects.create(nombre="Sede Norte")
        zona = ZonaObservador.objects.create(
            observador=obs, nombre="Zona Norte", perm_exportar=True)
        cuentas = []
        for i in range(1, 3):
            correo = "u%d@ejemplo.com" % i
            u = Usuario.objects.create_user(
                email=correo, password="x", nombre="Usuario %d" % i)
            cuentas.append(correo)
            for j in range(2):
                t = Ticket.objects.create(
                    titulo="Falla %d" % j, descripcion="d",
                    solicitante_nombre=u.nombre, solicitante_email=correo,
                    solicitante_punto=punto.nombre,
                    tecnico_asignado=tec, estado=Ticket.Estado.ABIERTO)
                TicketComentario.objects.create(
                    ticket=t, usuario=tec, autor_nombre="Tecnico Uno",
                    comentario="Voy en camino", es_interno=False)
            el = ElementoMiLista.objects.create(
                observador=obs, tipo=ElementoMiLista.TIPO_USUARIO,
                usuario_email=correo, usuario=u)
            el.zona = zona
            el.save()

        self.client.force_login(obs)
        r = self.client.get("/observador/mi-lista/")
        with open("/tmp/opencode/mi_lista_probe.html", "w", encoding="utf-8") as fh:
            fh.write(r.content.decode())
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        marca = html.find("pan-datos")
        print("TRAZA pan-datos:", repr(html[marca-120:marca+160]))
        crudo = html.split("pan-datos", 1)[1].split(">", 1)[1].split("</script>")[0]
        datos = json.loads(crudo)
        print("\nZONAS:", [z["nombre"] for z in datos["zonas"]])
        for z in datos["zonas"]:
            print("ZONA", z["nombre"], "cuentas", z["cuentas"],
                  "total", z["total"], "abiertos", z["abiertos"])
            for u in z["usuarios"]:
                print("  ", u["nombre"], u["email"],
                      "| total", u["total"], "abiertos", u["abiertos"],
                      "cerrados", u["cerrados"], "avance", u["avance"],
                      "| tickets", len(u["tickets"]),
                      "| respuestas", len(u["respuestas"]),
                      "| elemento", u["elemento_id"])
                if u["tickets"]:
                    print("      primer ticket:", u["tickets"][0])
                if u["respuestas"]:
                    print("      primer respuesta:", u["respuestas"][0])
        # La fila de mi-lista tambien lleva sus tickets
        for f in self.client.get("/observador/mi-lista/").context["filas"]:
            print("FILA", f["nombre"], "tickets", len(f["tickets"]),
                  "respuestas", len(f["respuestas"]), "total", f["total"])
