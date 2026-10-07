from django.core.management.base import BaseCommand
from apps.tickets.models import Categoria
from apps.tickets.sla import horas_por_prioridad

# Categorías alineadas al diagrama STATU QUO de Dogger S.A.S.
# (grupo, nombre, prioridad_ans)
CATEGORIAS = [
    # SIESA
    ("SIESA ERP", "Ventas y pedidos", "alta"),
    ("SIESA ERP", "Producción y bodega", "alta"),
    ("SIESA ERP", "Contabilidad y pagos", "alta"),
    ("SIESA ERP", "Facturación electrónica", "urgente"),
    ("SIESA ERP", "Reportes y tableros", "media"),
    # Comodin: cuando el reporte es del Siesa pero no se sabe el modulo.
    ("SIESA ERP", "Otros problemas de Siesa", "media"),
    ("SIESA Web", "Nomina Web", "media"),
    ("SIESA Web", "Autogestion", "media"),
    ("SIESA Web", "SiesaAccess", "media"),
    ("SIESA Cloud", "SIESA CLOUD-ERP", "alta"),
    # Puntos de venta / endpoints
    ("Puntos de venta", "POS Hardware", "urgente"),
    ("Puntos de venta", "POS Software", "urgente"),
    ("Puntos de venta", "Cajon Monedero", "media"),
    ("Puntos de venta", "Impresoras", "alta"),
    ("Puntos de venta", "POS Inventario y Precios", "alta"),
    ("Puntos de venta", "POS Lectores y Balanzas", "media"),
    ("Puntos de venta", "POS Sincronizacion y Datos", "alta"),
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
    ("Soporte TI", "Instalacion de Software", "media"),
    ("Soporte TI", "Actualizaciones y Parches", "baja"),
    ("Soporte TI", "Impresoras y Escaneres", "media"),
    ("Soporte TI", "Navegador y Aplicaciones Web", "media"),
    ("Soporte TI", "Microsoft 365 / Office", "media"),
    # Comodin: cuando el reporte no encaja en ninguna categoria de soporte.
    ("Soporte TI", "Otros problemas", "baja"),
    ("Administrativo TI", "Creacion Usuario", "baja"),
    ("Administrativo TI", "Permisos", "baja"),
    ("Administrativo TI", "Accesos", "media"),
    ("Administrativo TI", "Solicitud Equipo", "baja"),
]


class Command(BaseCommand):
    help = "Carga categorias Dogger alineadas a infraestructura STATU QUO + SIESA, POS y soporte TI"

    def handle(self, *args, **options):
        creadas = 0
        actualizadas = 0
        for grupo, nombre, prioridad in CATEGORIAS:
            cat, created = Categoria.objects.get_or_create(
                grupo=grupo,
                nombre=nombre,
                defaults={"activo": True, "prioridad_default": prioridad, "ans_horas": horas_por_prioridad(prioridad)},
            )
            if created:
                creadas += 1
            elif cat.prioridad_default != prioridad or cat.ans_horas != horas_por_prioridad(prioridad):
                cat.prioridad_default = prioridad
                cat.ans_horas = horas_por_prioridad(prioridad)
                cat.save(update_fields=["prioridad_default", "ans_horas"])
                actualizadas += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Categorias listas. Nuevas: {creadas} / Actualizadas: {actualizadas} / Total catálogo: {len(CATEGORIAS)}"
            )
        )
