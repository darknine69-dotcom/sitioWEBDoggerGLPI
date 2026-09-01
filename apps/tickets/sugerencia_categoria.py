"""
Sugerencia automática de categoría según el título/descripción del ticket.

Las claves se definen por categoría ("grupo::nombre") con sinónimos típicos
del lenguaje de los usuarios de Dogger. Sirve tanto en el servidor (asignar
automáticamente si el usuario dejó la categoría vacía) como en el cliente
(marcar sugerencia mientras escribe el ticket).
"""
import re
import unicodedata

from django.db.models import Count

from .models import Categoria

PALABRAS_CLAVE = {
    # ---- SIESA ERP ----
    "SIESA ERP::Comercial": [
        "facturacion", "factura", "facturar", "pedido", "cotizacion", "cliente",
        "lista de precios", "precios", "descuento", "despacho", "inventario", "comercial",
    ],
    "SIESA ERP::Manufactura": [
        "produccion", "manufactura", "formula", "receta", "orden de produccion", "lote",
        "vencimiento", "calidad", "bodega", "materia prima",
    ],
    "SIESA ERP::Financiero": [
        "contabilidad", "contabilizacion", "financiero", "impuesto", "retencion", "pago",
        "cuenta por pagar", "cuenta por cobrar", "banco", "conciliacion", "cartera",
        "presupuesto", "tesoreria",
    ],
    "SIESA ERP::POS-FE": [
        "pos", "pos-fe", "caja", "cajero", "factura", "facturacion", "fiscal",
        "impresora fiscal", "venta", "ticket de venta", "cierre de caja", "arqueo",
        "facturador", "pos no imprime", "no imprime el ticket", "no imprime tickets",
    ],
    "SIESA ERP::Biable": [
        "biable", "business intelligence", "reporte gerencial", "dashboard", "kpi", "inteligencia",
    ],
    # ---- SIESA Web ----
    "SIESA Web::Nomina Web": [
        "nomina", "salario", "prestaciones", "prima", "vacaciones", "cesantias",
        "autoliquidacion", "novedad de nomina", "liquidacion",
    ],
    "SIESA Web::Autogestion": [
        "autogestion", "comprobante", "certificado", "siesa web", "empleado", "consulta de nomina",
    ],
    "SIESA Web::SiesaAccess": [
        "siesa access", "siesaaccess", "aplicativo movil", "celular", "acceso remoto", "vpn siesa",
    ],
    "SIESA Cloud::SIESA CLOUD-ERP": [
        "siesa cloud", "cloud erp", "nube", "servidor siesa", "siesa en la nube",
    ],
    # ---- Puntos de venta ----
    "Puntos de venta::POS Hardware": [
        "no prende", "no enciende", "se apaga", "pantalla", "touch", "lector", "scanner",
        "lector de codigo", "pc pos", "pc-p", "hardware", "falla fisica", "tarjeta",
    ],
    "Puntos de venta::POS Software": [
        "software", "se traba", "se cierra", "lentitud", "pantallazo", "error del pos",
        "actualizar pos", "version del pos", "configuracion pos", "congela",
    ],
    "Puntos de venta::Cajon Monedero": [
        "cajon", "monedero", "no abre el cajon", "cajon de monedas", "llave del cajon",
    ],
    "Puntos de venta::Impresoras": [
        "impresora", "no imprime", "impresion", "cabezal", "papel", "cola de impresion",
        "impresora compartida", "driver impresora", "impresora de tickets",
    ],
    # ---- Endpoints ----
    "Endpoints::PC / Laptop": [
        "pc", "computador", "laptop", "portatil", "no enciende", "lento", "pantalla azul",
        "disco duro", "ram", "teclado", "mouse", "reinicia solo",
    ],
    "Endpoints::Perifericos": [
        "periferico", "teclado", "mouse", "video beamer", "proyector", "parlante",
        "auricular", "webcam", "tablet", "manos libres",
    ],
    # ---- Infraestructura ----
    "Infraestructura::Red / Switch": [
        "red", "switch", "no hay red", "internet", "wifi", "cable", "conexion", "puerto",
        "vlan", "datos", "navegacion", "router", "caida de red",
    ],
    "Infraestructura::Firewall Fortinet": [
        "fortinet", "fortigate", "firewall", "bloqueo de pagina", "filtrado", "vpn",
        "seguridad perimetral", "paginas bloqueadas",
    ],
    "Infraestructura::WatchGuard": [
        "watchguard", "firewall watchguard",
    ],
    "Infraestructura::Server Principal": [
        "server principal", "servidor principal", "servidor", "hyper-v", "virtualizacion",
        "vm", "se cayo el servidor", "reiniciar servidor",
    ],
    "Infraestructura::Terminal Server": [
        "terminal server", "rds", "escritorio remoto", "sesion", "servidor de terminales",
        "licencias rds", "no me deja entrar",
    ],
    "Infraestructura::Servidor de Archivos": [
        "servidor de archivos", "archivos", "carpeta compartida", "unit", "file server",
        "compartido",
    ],
    "Infraestructura::Servidor de Correos": [
        "servidor de correos", "correo no llega", "exchange", "buzon", "correos salientes",
        "correos entrantes", "correo se devuelve",
    ],
    "Infraestructura::Backup": [
        "backup", "respaldo", "copia de seguridad", "restauracion", "data backup",
    ],
    "Infraestructura::Antivirus / Consola": [
        "antivirus", "consola", "virus", "malware", "infeccion", "proteccion", "endpoint security",
    ],
    "Infraestructura::Sistema de Marcacion": [
        "marcacion", "biometrico", "huella", "reloj", "asistencia", "marcaje", "entrada y salida",
    ],
    # ---- Integraciones ----
    "Integraciones::GenericTransfer": [
        "generic transfer", "generictransfer", "transferencia", "interface", "intercambio",
        "comunicacion entre sistemas", "integracion siesa",
    ],
    "Integraciones::Web Service": [
        "web service", "webservice", "api", "servicios web", "rest", "soap",
    ],
    "Integraciones::Correos HUGE": [
        "correos huge", "huge", "correo corporativo",
    ],
    # ---- Soporte TI ----
    "Soporte TI::Hardware": [
        "equipo", "falla fisica", "repuesto", "garantia", "hardware", "componente",
    ],
    "Soporte TI::Software": [
        "instalacion", "aplicacion", "office", "windows", "programa", "actualizacion",
        "licencia de software", "instalar",
    ],
    "Soporte TI::Correo": [
        "correo", "outlook", "email", "buzon", "no recibo correo", "no puedo enviar correo",
        "spam", "contrasena de correo",
    ],
    "Soporte TI::Red": [
        "internet", "wifi", "cable de red", "conectividad", "impresora de red", "sin red",
    ],
    # ---- Administrativo TI ----
    "Administrativo TI::Creacion Usuario": [
        "crear usuario", "creacion de usuario", "nuevo usuario", "cuenta nueva",
        "alta de usuario", "usuario directorio", "crear cuenta", "crear un usuario",
        "usuario nuevo", "crear usuario nuevo", "no puedo crear usuario",
        "creacion del usuario",
    ],
    "Administrativo TI::Permisos": [
        "permisos", "permiso de acceso", "carpeta compartida", "acceso a carpeta",
        "permisos de red", "roles", "no tengo permisos",
    ],
    "Administrativo TI::Accesos": [
        "accesos", "acceso", "credenciales", "contrasena", "desbloquear", "bloqueado",
        "no me deja ingresar", "usuario bloqueado", "acceso a sistemas",
    ],
    "Administrativo TI::Solicitud Equipo": [
        "solicitud de equipo", "equipo nuevo", "computador nuevo", "cambio de equipo",
        "laptop nueva", "dotacion", "compra de equipo", "nuevo computador",
    ],
}


def _norm(texto):
    return "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )


def _puntaje(texto, categoria):
    """Devuelve un puntaje de coincidencia entre el texto plano y una categoría."""
    claves = PALABRAS_CLAVE.get(f"{categoria.grupo}::{categoria.nombre}", [])
    score = 0
    for clave in claves:
        k = _norm(clave)
        if not k:
            continue
        if " " in k:
            if k in texto:
                score += 4
        else:
            if re.search(r"\b" + re.escape(k) + r"\b", texto):
                score += 2
            elif k in texto:
                score += 1
    if _norm(categoria.nombre) in texto:
        score += 2
    if _norm(categoria.grupo) in texto:
        score += 1
    return score


UMBRAL_MINIMO = 2


def sugerir_categoria(titulo="", descripcion="", excluir=None):
    """
    Devuelve la Categoría más probable según el texto, o None si no hay
    una coincidencia clara (puntaje >= umbral).
    """
    texto = _norm(f"{titulo} {descripcion}")
    if len(texto.strip()) < 8:
        return None
    mejor = None
    mejor_puntaje = 0
    qs = Categoria.objects.annotate(n_tickets=Count("tickets"))
    if excluir:
        qs = qs.exclude(pk=excluir)
    for cat in qs.filter(activo=True):
        p = _puntaje(texto, cat)
        if p > mejor_puntaje:
            mejor = cat
            mejor_puntaje = p
    return mejor if mejor_puntaje >= UMBRAL_MINIMO else None


def claves_para_json():
    """Lista serializable para el sugeridor en el cliente."""
    datos = []
    for cat in Categoria.objects.filter(activo=True).order_by("grupo", "nombre"):
        datos.append({
            "id": cat.pk,
            "grupo": cat.grupo,
            "nombre": cat.nombre,
            "claves": PALABRAS_CLAVE.get(f"{cat.grupo}::{cat.nombre}", []),
        })
    return datos