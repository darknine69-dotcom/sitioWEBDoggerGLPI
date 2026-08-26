import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tickets.models import Categoria, Ticket

User = get_user_model()

SOLICITANTES = [
    {
        "nombre": "Andrés Felipe Moreno",
        "email": "andres.moreno@dogger.com.co",
        "telefono": "310 456 7891",
    },
    {
        "nombre": "Diana Carolina Ríos",
        "email": "diana.rios@dogger.com.co",
        "telefono": "315 678 2345",
    },
    {
        "nombre": "Julián David Ospina",
        "email": "julian.ospina@dogger.com.co",
        "telefono": "320 890 1234",
    },
    {
        "nombre": "Laura Valentina Restrepo",
        "email": "laura.restrepo@dogger.com.co",
        "telefono": "301 234 5678",
    },
    {
        "nombre": "Santiago Henao Cardona",
        "email": "santiago.henao@dogger.com.co",
        "telefono": "302 345 6789",
    },
]

TICKETS_PRUEBA = [
    # Andrés Felipe Moreno - 2 tickets
    {
        "solicitante": "andres.moreno@dogger.com.co",
        "titulo": "POS-FE no imprime facturas en Caja 5",
        "descripcion": "La impresora del punto de venta Caja 5 (Envigado) no responde al intentar imprimir facturas electrónicas. El error muestra 'Puerto COM no disponible'. Ya se verificó el cable y la impresora enciende normalmente.",
        "punto": "Envigado · Caja 5",
        "cat_grupo": "Puntos de venta",
        "cat_nombre": "Impresoras",
        "estado": "abierto",
    },
    {
        "solicitante": "andres.moreno@dogger.com.co",
        "titulo": "SIESA Access lento al consultar inventarios",
        "descripcion": "Al acceder al módulo de inventarios en SIESA Access tarda más de 3 minutos en cargar. El problema ocurre solo en la sede de Envigado. En Bogotá funciona normal.",
        "punto": "Envigado · PC-P3",
        "cat_grupo": "SIESA Web",
        "cat_nombre": "SiesaAccess",
        "estado": "en-progreso",
    },
    # Diana Carolina Ríos - 1 ticket
    {
        "solicitante": "diana.rios@dogger.com.co",
        "titulo": "Servidor de backup no responde",
        "descripcion": "El servidor de backup no está respondiendo desde esta mañana. No se han ejecutado los respaldos nocturnos. El servidor muestra luz de poder pero no responde a ping.",
        "punto": "Bogotá · Server Backup",
        "cat_grupo": "Infraestructura",
        "cat_nombre": "Backup",
        "estado": "en-progreso",
    },
    # Julián David Ospina - 1 ticket
    {
        "solicitante": "julian.ospina@dogger.com.co",
        "titulo": "Firewall bloqueando acceso a correo externo",
        "descripcion": "Desde ayer los usuarios no pueden recibir correos de clientes externos. El firewall Fortinet parece estar bloqueando el puerto 993. Necesitamos revisar las reglas de firewall urgentemente.",
        "punto": "Bogotá · Server Principal",
        "cat_grupo": "Infraestructura",
        "cat_nombre": "Firewall Fortinet",
        "estado": "resuelto",
    },
    # Laura Valentina Restrepo - 1 ticket
    {
        "solicitante": "laura.restrepo@dogger.com.co",
        "titulo": "Laptop con pantalla parpadeando",
        "descripcion": "La laptop del contable presenta parpadeo constante en la pantalla. Ya se intentó cambiar el cable LVDS pero el problema persiste. Posible falla en la pantalla o la GPU.",
        "punto": "Envigado · Oficina Contable",
        "cat_grupo": "Endpoints",
        "cat_nombre": "PC / Laptop",
        "estado": "cerrado",
    },
    # Santiago Henao Cardona - 1 ticket
    {
        "solicitante": "santiago.henao@dogger.com.co",
        "titulo": "Solicitud de usuario nuevo en SIESA",
        "descripcion": "Se necesita crear un usuario nuevo en SIESA ERP para el nuevo empleado del commercial. Nombre: Juan Pérez, departamento: Ventas.",
        "punto": "Bogotá · Oficinas",
        "cat_grupo": "Administrativo TI",
        "cat_nombre": "Creacion Usuario",
        "estado": "resuelto",
    },
]


class Command(BaseCommand):
    help = "Crea 5 solicitantes con tickets realistas para demostración"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Eliminar datos de prueba existentes antes de crear nuevos",
        )

    def handle(self, *args, **options):
        if options["clean"]:
            self._limpiar()

        tecnicos = list(
            User.objects.filter(rol__in=["admin", "tecnico"], activo=True).order_by("?")[:3]
        )
        if not tecnicos:
            self.stdout.write(self.style.WARNING("No hay técnicos/admins disponibles."))
            return

        # Crear usuarios solicitantes (rol usuario)
        usuarios_map = {}
        for data in SOLICITANTES:
            user, created = User.objects.get_or_create(
                email=data["email"],
                defaults={
                    "nombre": data["nombre"],
                    "rol": "usuario",
                    "telefono": data["telefono"],
                    "activo": True,
                },
            )
            if created:
                user.set_password("dogger1234")
                user.save()
            usuarios_map[data["email"]] = user

        self.stdout.write(f"Solicitantes: {len(usuarios_map)}")

        # Crear tickets con fechas variadas (últimos 10 días, horas al azar)
        tickets_creados = 0
        ahora = timezone.now()
        dias_base = [0, 1, 2, 3, 5, 7]  # Distribución desigual más realista
        horas_posibles = [8, 9, 10, 11, 13, 14, 15, 16, 17]
        minutos_posibles = [0, 5, 10, 15, 20, 30, 45]

        for tdata in TICKETS_PRUEBA:
            email = tdata["solicitante"]
            user = usuarios_map.get(email)
            if not user:
                continue

            cat = Categoria.objects.filter(
                grupo=tdata["cat_grupo"],
                nombre=tdata["cat_nombre"],
            ).first()

            prioridad = cat.prioridad_default if cat else "media"
            estado = tdata["estado"]

            tecnico = random.choice(tecnicos)

            # Fecha variada
            dias_atras = random.choice(dias_base)
            hora = random.choice(horas_posibles)
            minuto = random.choice(minutos_posibles)
            fecha_creacion = ahora - timedelta(days=dias_atras)
            fecha_creacion = fecha_creacion.replace(hour=hora, minute=minuto, second=random.randint(0, 59))

            ticket = Ticket(
                titulo=tdata["titulo"],
                descripcion=tdata["descripcion"],
                prioridad=prioridad,
                categoria=cat,
                estado=estado,
                solicitante_nombre=user.nombre,
                solicitante_email=user.email,
                solicitante_punto=tdata["punto"],
                tecnico_asignado=tecnico,
                asignacion_automatica=cat is not None and cat.tecnico_default is not None,
            )
            ticket.save()
            # Forzar fecha de creación y cierre realistas
            updates = {"fecha_creacion": fecha_creacion}
            if estado in ("resuelto", "cerrado"):
                # Cierre entre 1h y 48h después de creación
                horas_cierre = random.randint(1, 48)
                updates["fecha_cierre"] = fecha_creacion + timedelta(hours=horas_cierre)
            Ticket.objects.filter(pk=ticket.pk).update(**updates)
            tickets_creados += 1

        self.stdout.write(
            self.style.SUCCESS(f"Listo: {len(usuarios_map)} solicitantes, {tickets_creados} tickets")
        )

    def _limpiar(self):
        emails = [s["email"] for s in SOLICITANTES]
        Ticket.objects.filter(solicitante_email__in=emails).delete()
        User.objects.filter(email__in=emails).delete()
        self.stdout.write("Datos de prueba anteriores eliminados.")
