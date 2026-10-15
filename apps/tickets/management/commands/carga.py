"""Tráfico simulado contra las vistas calientes, antes de producción.

Uso:
    DOGGER_CARGA=1 python manage.py carga --hilos 4 --peticiones 30
    DOGGER_CARGA=1 python manage.py carga --hilos 8 --peticiones 50 --con-escritura

Siembra datos con prefijo CARGA- (los borra al final) y reparte GETs de
lectura entre hilos con su propio cliente. Reporta media/p50/p95/máximo
por vista y cuenta errores (status inesperado o excepción). Sin
`DOGGER_CARGA=1` se niega a correr: nunca contra producción sin querer.
"""

import os
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse


class Command(BaseCommand):
    help = "Simula tráfico concurrente de lectura sobre las vistas calientes."

    def add_arguments(self, parser):
        parser.add_argument("--hilos", type=int, default=4)
        parser.add_argument("--peticiones", type=int, default=30,
                            help="Peticiones por hilo.")
        parser.add_argument("--con-escritura", action="store_true",
                            help="Incluye 1 POST de chat por hilo.")

    def handle(self, *args, **options):
        if os.getenv("DOGGER_CARGA", "") != "1":
            raise CommandError(
                "Por seguridad exige DOGGER_CARGA=1 (nunca en producción real)."
            )
        from django.contrib.auth import get_user_model

        from apps.tickets.models import Ticket

        User = get_user_model()
        hilos = max(1, options["hilos"])
        por_hilo = max(1, options["peticiones"])
        con_escritura = options["con_escritura"]

        self.stdout.write("Sembrando datos CARGA- …")
        admin = User.objects.create_user(
            email="carga-admin@test.local", nombre="Carga Admin",
            password="x", rol="admin", is_staff=True)
        tec = User.objects.create_user(
            email="carga-tec@test.local", nombre="Carga Tec",
            password="x", rol="tecnico")
        usu = User.objects.create_user(
            email="carga-usu@test.local", nombre="Carga Usu",
            password="x", rol="usuario")
        tickets = [
            Ticket.objects.create(
                titulo=f"CARGA-{i}", descripcion="d",
                solicitante_nombre="Carga Usu",
                solicitante_email="carga-usu@test.local",
                tecnico_asignado=tec,
            )
            for i in range(5)
        ]

        planes = [
            (admin, [("dashboard", reverse("tickets:dashboard"), ())] * 2 + [
                ("lista", reverse("tickets:lista"), ()),
                ("reportes", reverse("tickets:reportes"), ()),
                ("usuarios", reverse("tickets:usuarios"), ()),
                ("chat_tickets", reverse("tickets:chat_tickets"), ()),
                ("chat_colegas", reverse("tickets:chat_colegas"), ()),
                ("notif_api", reverse("notificaciones:api"), ()),
            ]),
            (tec, [
                ("panel_tecnico", reverse("tickets:panel_tecnico"), ()),
                ("lista", reverse("tickets:lista"), ()),
                ("chat_tickets", reverse("tickets:chat_tickets"), ()),
            ]),
            (usu, [
                ("mi_panel", reverse("tickets:mi_panel"), ()),
                ("mi_ticket", reverse("tickets:mi_ticket", args=[tickets[0].pk]), ()),
                ("chat_tickets", reverse("tickets:chat_tickets"), ()),
                ("chat_hilo", reverse("tickets:chat_hilo", args=[tickets[0].pk]), ()),
            ]),
        ]
        if con_escritura:
            planes[2][1].append(
                ("chat_post", reverse("tickets:chat_responder", args=[tickets[0].pk]),
                 {"mensaje": "ping de carga"}))

        # Calentamiento: valida que cada URL da 200 una vez.
        sonda = Client()
        for usuario, rutas in planes:
            sonda.force_login(usuario)
            for nombre, url, _ in rutas:
                r = sonda.get(url)
                if r.status_code != 200:
                    self._limpiar(User, Ticket)
                    raise CommandError(f"Calentamiento falló: {nombre} -> {r.status_code}")

        tiempos = {}
        errores = []
        candado = threading.Lock()

        def _golpear(usuario, rutas, n):
            cliente = Client()
            cliente.force_login(usuario)
            for i in range(n):
                nombre, url, datos = rutas[i % len(rutas)]
                t0 = time.perf_counter()
                try:
                    if nombre == "chat_post":
                        r = cliente.post(url, datos)
                    else:
                        r = cliente.get(url)
                    dt = (time.perf_counter() - t0) * 1000
                    with candado:
                        tiempos.setdefault(nombre, []).append(dt)
                        if r.status_code != 200:
                            errores.append(f"{nombre} -> HTTP {r.status_code}")
                except Exception as exc:  # noqa: BLE001 - el error ES el dato
                    with candado:
                        errores.append(f"{nombre} -> {exc.__class__.__name__}: {exc}")

        try:
            with ThreadPoolExecutor(max_workers=hilos) as pool:
                futs = []
                for h in range(hilos):
                    usuario, rutas = planes[h % len(planes)]
                    futs.append(pool.submit(_golpear, usuario, rutas, por_hilo))
                for f in futs:
                    f.result()
        finally:
            self._limpiar(User, Ticket)

        total = sum(len(v) for v in tiempos.values())
        self.stdout.write(f"\n{hilos} hilos x {por_hilo} = {total} peticiones")
        for nombre in sorted(tiempos):
            lat = sorted(tiempos[nombre])
            p50 = lat[len(lat) // 2]
            p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
            self.stdout.write(
                f"  {nombre:<15} n={len(lat):<4} media={statistics.mean(lat):7.1f}ms "
                f"p50={p50:7.1f}ms p95={p95:7.1f}ms max={lat[-1]:7.1f}ms")
        if errores:
            self.stdout.write(self.style.ERROR(f"\n{len(errores)} ERRORES:"))
            vistos = {}
            for e in errores:
                vistos[e] = vistos.get(e, 0) + 1
            for e, n in sorted(vistos.items(), key=lambda x: -x[1])[:10]:
                self.stdout.write(f"  {n}x {e}")
        else:
            self.stdout.write(self.style.SUCCESS("\nSin errores."))

    def _limpiar(self, User, Ticket):
        Ticket.objects.filter(titulo__startswith="CARGA-").delete()
        User.objects.filter(email__contains="carga-").delete()
