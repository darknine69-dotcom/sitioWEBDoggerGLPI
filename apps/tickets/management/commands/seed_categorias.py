from django.core.management.base import BaseCommand
from apps.tickets.models import Categoria

# Categorías alineadas al diagrama STATU QUO de Dogger S.A.S.
# (grupo, nombre, prioridad_ans)
CATEGORIAS = [
    # SIESA
    ("SIESA ERP", "Comercial", "alta"),
    ("SIESA ERP", "Manufactura", "alta"),
    ("SIESA ERP", "Financiero", "alta"),
    ("SIESA ERP", "POS-FE", "urgente"),
    ("SIESA ERP", "Biable", "media"),
    ("SIESA Web", "Nomina Web", "media"),
    ("SIESA Web", "Autogestion", "media"),
    ("SIESA Web", "SiesaAccess", "media"),
    ("SIESA Cloud", "SIESA CLOUD-ERP", "alta"),
    # Puntos de venta / endpoints
    ("Puntos de venta", "POS Hardware", "urgente"),
    ("Puntos de venta", "POS Software", "urgente"),
    ("Puntos de venta", "Cajon Monedero", "media"),
    ("Puntos de venta", "Impresoras", "alta"),
    ("Endpoints", "PC / Laptop", "media"),
    ("Endpoints", "Perifericos", "baja"),
    # Infraestructura de red y servidores (diagrama)
    ("Infraestructura", "Red / Switch", "urgente"),
    ("Infraestructura", "Firewall Fortinet", "urgente"),
    ("Infraestructura", "WatchGuard", "urgente"),
    ("Infraestructura", "Server Principal", "urgente"),
    ("Infraestructura", "Terminal Server", "alta"),
    ("Infraestructura", "Servidor de Archivos", "alta"),
    ("Infraestructura", "Servidor de Correos", "alta"),
    ("Infraestructura", "Backup", "urgente"),
    ("Infraestructura", "Antivirus / Consola", "media"),
    ("Infraestructura", "Sistema de Marcacion", "media"),
    # Integraciones
    ("Integraciones", "GenericTransfer", "alta"),
    ("Integraciones", "Web Service", "media"),
    ("Integraciones", "Correos HUGE", "alta"),
    # Soporte TI clasico
    ("Soporte TI", "Hardware", "media"),
    ("Soporte TI", "Software", "media"),
    ("Soporte TI", "Correo", "media"),
    ("Soporte TI", "Red", "media"),
    ("Administrativo TI", "Creacion Usuario", "baja"),
    ("Administrativo TI", "Permisos", "baja"),
    ("Administrativo TI", "Accesos", "media"),
    ("Administrativo TI", "Solicitud Equipo", "baja"),
]


class Command(BaseCommand):
    help = "Carga categorias Dogger alineadas a infraestructura STATU QUO + SIESA"

    def handle(self, *args, **options):
        creadas = 0
        actualizadas = 0
        for grupo, nombre, prioridad in CATEGORIAS:
            cat, created = Categoria.objects.get_or_create(
                grupo=grupo,
                nombre=nombre,
                defaults={"activo": True, "prioridad_default": prioridad},
            )
            if created:
                creadas += 1
            elif cat.prioridad_default != prioridad:
                cat.prioridad_default = prioridad
                cat.save(update_fields=["prioridad_default"])
                actualizadas += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Categorias listas. Nuevas: {creadas} / Actualizadas: {actualizadas} / Total catálogo: {len(CATEGORIAS)}"
            )
        )
