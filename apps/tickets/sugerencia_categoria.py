"""
Sugerencia automática de categoría según el título/descripción del ticket.

Las claves se definen por categoría ("grupo::nombre") con la forma en que los
usuarios de Dogger cuentan el problema: "no prende el cajón", "no me deja
entrar al correo", "el sistema está que no carga". Sirve en dos sitios con el
mismo criterio:

  * en el servidor, para asignar la categoría cuando el usuario la dejó vacía;
  * en el cliente (`claves_para_json`), para mover la categoría mientras
    escribe, sin recargar la página.

Hay tres capas de palabras, de la más específica a la más general:

  1. PALABRAS_CLAVE: los problemas típicos de cada categoría (pesan 3 y 6).
  2. PALABRAS_EXCLUYE: contexto que descarta la categoría, para que lo del POS
     no se coma lo de la oficina ("de la oficina" saca las impresoras del POS).
  3. Categorías comodín ("Otros problemas de Siesa", "Otros problemas"): lo que no tiene
     categoría clara cae en la del dominio, nunca se queda sin rellenar.

El puntaje se calcula aquí y se replica en `static/js/dogger.js`, así que
cualquier cambio en los pesos debe hacerse en los dos lados.
"""
import re
import unicodedata

from .models import Categoria

# Peso de cada tipo de coincidencia. El título pesa más que la descripción:
# es lo que la persona escribe primero y lo más específico.
PESO_FRASE = 6
PESO_PALABRA = 3
PESO_PALABRA_SUELTA = 1
PESO_NOMBRE = 3
PESO_GRUPO = 1
# Multiplicador para las coincidencias que aparecen en el título.
PESO_TITULO = 2
# Pesa más que una frase (6): si el texto dice "de la oficina", la categoría
# del POS queda por debajo de la de soporte TI aunque mentione el problema.
PESO_EXCLUYE = 8
# Cuántas palabras de contexto negativo se acumulan como máximo, para que un
# texto muy cargado no deje el puntaje en negativo sin fin.
MAXIMO_EXCLUSIONES = 2

PALABRAS_CLAVE = {
    # ================= SIESA ERP: módulo por módulo =================
    "SIESA ERP::Ventas y pedidos": [
        "facturacion", "factura", "facturar", "facturado", "pedido", "cotizacion",
        "cliente", "lista de precios", "precios", "precio", "descuento", "despacho",
        "inventario", "comercial", "orden de compra", "cartera de clientes",
        "cliente nuevo", "credito", "cartera", "remision", "guias", "precio de venta",
        "margen", "orden de venta", "entrada de mercancia", "nota de venta",
        "cuenta por cobrar", "cliente sin facturar", "no me deja facturar", "secuencia",
        "numero de documento", "resolucion de numeracion", "precio de compra",
        "no guarda la venta", "utilidad", "margen de utilidad",
        "contacto del cliente", "ciudad del cliente", "datos del cliente",
        "no aparece el cliente", "no aparece el producto", "saldo del cliente",
        "forma de pago", "pago en cuotas", "abono", "anticipo", "retencion en la fuente",
    ],
    "SIESA ERP::Producción y bodega": [
        "produccion", "manufactura", "formula", "receta", "orden de produccion", "lote",
        "vencimiento", "calidad", "bodega", "materia prima", "plan de produccion",
        "consumo", "despacho de produccion", "serial", "lote de produccion",
        "secuencia", "centro de trabajo", "reproceso", "programa de produccion",
        "orden de compra de produccion", "hoja de vida", "costo de produccion",
        "no produce", "no genera la produccion", "rendimiento", "merma",
        "control de calidad", "lote vencido", "producto en proceso", "wip",
    ],
    "SIESA ERP::Contabilidad y pagos": [
        "contabilidad", "contabilizacion", "financiero", "impuesto", "retencion", "pago",
        "cuenta por pagar", "cuenta por cobrar", "banco", "conciliacion", "cartera",
        "presupuesto", "tesoreria", "recibo de pago", "cuadre contable", "auxiliar",
        "nomina electronica", "provisiones", "activo fijo", "depreciacion",
        "no cuadra la contabilidad", "descuadre contable", "asiento contable",
        "mayorAuxiliar", "partida doble", "centro de costo", "tercero",
        "no puedo pagar", "no puedo cobrar", "comprobante de pago", "cheque",
        "transaccion bancaria", "obligacion tributaria", "declaracion",
        "impuesto a las ventas", "retencion en la fuente",
    ],
    "SIESA ERP::Facturación electrónica": [
        "pos-fe", "caja", "cajero", "factura", "facturacion", "fiscal",
        "impresora fiscal", "venta", "ticket de venta", "cierre de caja", "arqueo",
        "facturador", "pos no imprime", "no imprime el ticket", "no imprime tickets",
        "documento equivalente", "pos fe", "punto de venta", "siesa pos",
        "sistema del pos", "caja del punto de venta", "apertura de caja", "cierre de dia",
        "fondo de caja", "base de caja", "sobrante", "faltante", "cuadre de caja",
        "corte de caja", "cambio de turno", "turno de caja", "modo caja",
        "secuencia de factura", "tarjeta de operador", "pin de operador",
        "no me abre el pos", "pos no arranca", "error del pos fe",
        "no permite facturar", "rechazo de la factura", "la caja no cuadra",
        "pos de dogger", "siesa del punto de venta", "pv", "pdv",
        # Facturacion electronica: sirve en el ERP y en el POS.
        "factura electronica", "facturacion electronica", "dian", "cufe", "cue",
        "no factura", "no puedo facturar", "error de facturacion", "factura rechazada",
        "documento no valido", "documento invalido", "servicio de facturacion",
        "resolucion de facturacion", "autorizacion de la factura", "qr de la factura",
        "factura sin cufe", "punto de venta electronico", "pvfe", "factura digital",
        "no imprime la factura", "certificado digital", "firma digital",
        "notificacion de factura", "correo de la factura", "rangos de numeracion",
        "habilitacion de la factura", "facturar", "error al facturar",
        "error facturando", "no me deja facturar", "no logro facturar",
        "sistema de facturacion", "documento rechazado", "cufe no llega",
        "no llega el cufe", "factura electronica no envia", "error dian",
        "nota de venta electronica", "no llega la factura", "factura no llega",
    ],
    "SIESA ERP::Reportes y tableros": [
        "biable", "business intelligence", "reporte gerencial", "dashboard", "kpi",
        # La palabra suelta "reporte" es la que mas se escribe; sin ella un
        # "no me abre el reporte de ventas" se iba a la categoria del cajon.
        "reporte de ventas", "reporte de inventario", "reporte de produccion",
        "reporte", "reportes", "informe", "informes", "consulta de reportes",
        "inteligencia", "indicadores", "tablero de control", "consulta gerencial",
        "reporte en siiesa", "informes", "consulta de reportes", "tablero de siiesa",
        "grafico", "analisis de ventas", "semaforo", "tablero",
    ],
    "SIESA ERP::Otros problemas de Siesa": [
        "siesa", "sistema", "sistema siesa", "modulo",
        "no me deja", "no funciona", "no abre", "no carga", "no me deja entrar",
        "aplicativo siesa", "ayuda siesa", "problema siesa", "no entra siesa",
        "siesa se sale", "siesa se cierra", "no guarda siesa", "reporte siesa",
        "no se que modulo", "no ubico el problema", "problema siesa erp",
        "version siesa", "actualizar siesa",
    ],
    # ================= SIESA Web / Cloud =================
    "SIESA Web::Nomina Web": [
        "nomina", "salario", "prestaciones", "prima", "vacaciones", "cesantias",
        "autoliquidacion", "novedad de nomina", "liquidacion", "liquidar nomina",
        "colaborador", "empleado en nomina", "no me paga", "error en la nomina",
        "certificado de nomina", "desprendible", "nomina electronica",
        "novedad", "incapacidad", "permiso", "ausencia",
    ],
    "SIESA Web::Autogestion": [
        "autogestion", "comprobante", "certificado", "siesa web", "empleado",
        "consulta de nomina", "portaela", "consulta de comprobantes",
        "descargar certificado", "constancia", "tramite en siesa web",
    ],
    "SIESA Web::SiesaAccess": [
        "siesa access", "siesaaccess", "aplicativo movil", "celular", "acceso remoto",
        "vpn siesa", "acceso a siesa desde el celular", "siesa en la tablet",
        "no entra el acceso", "acceso remoto a siesa", "certificado de acceso",
    ],
    "SIESA Cloud::SIESA CLOUD-ERP": [
        "siesa cloud", "cloud erp", "nube", "servidor siesa", "siesa en la nube",
        "cloud", "se cae el cloud", "no entra al cloud",
    ],
    # ================= Puntos de venta =================
    "Puntos de venta::POS Hardware": [
        "no prende", "no enciende", "se apaga", "pantalla", "touch",
        "pc pos", "pc-p", "hardware", "falla fisica", "tarjeta",
        "terminal", "terminal pos", "pc de caja", "caja no prende", "pantalla del pos",
        "se apaga la caja", "problema fisico", "cambio de equipo", "equipo de caja",
        "botonera", "teclado del pos", "caja se reinicia", "pos no arranca",
        "cargador", "bateria", "no enciende el equipo", "hardware del pos",
        "pc del punto de venta", "equipo del punto de venta", "caja del punto de venta",
        "terminal del punto de venta", "hardware del punto de venta",
        "pincho", "usb", "conector", "placa mother", "cambio de fuente",
        "pc p1", "pc p2", "pc p3", "pc p4", "pc p5", "equipo de punto de venta",
        "se rompio el equipo", "no arranca el pc", "la pantalla no enciende",
        "teclado del punto de venta", "cambio de teclado", "mouse del pos",
        "se reinicia solo", "pantalla con rayas", "no toca la pantalla",
        "no enciende la caja", "equipo de la caja", "pc del local",
        "no arranca", "no responde", "se reinicia",
    ],
    "Puntos de venta::POS Software": [
        "software", "se traba", "se cierra", "lentitud", "pantallazo", "error del pos",
        "actualizar pos", "version del pos", "configuracion pos", "congela",
        "pos no abre", "no me deja abrir el pos", "aplicacion del pos",
        "error de pos", "se bloquea", "se cuelga", "reinicia solo el pos",
        "base de datos del pos", "respaldo del pos", "programa del punto de venta",
        "no abre el software", "falla del programa", "error de sistema del pos",
        "pos muestra error", "no me deja cobrar", "no registra la venta", "venta no se guarda",
        "pos se sale", "pos no carga", "se queda cargando", "proceso del pos",
        "instalar el pos", "actualizacion del pos", "pos no tiene licencia",
        "programa del pos", "se reinicia el pos", "pos queda lento",
        "no abre el menu", "no me deja entrar al pos", "sesion del pos",
        "lenta", "lento", "va lento", "tarda", "tarda mucho", "demora",
        "se queda pensando", "se queda pensando mucho", "no renderiza",
        "pos lento", "maquina del punto de venta", "equipo del punto de venta esta lento",
    ],
    "Puntos de venta::POS Inventario y Precios": [
        "inventario", "no carga el catalogo", "productos", "precios", "cambiar precio",
        "no aparecen los productos", "catalogo", "stock", "existencia",
        "conteo de inventario", "no cuadra el inventario", "ajuste de inventario",
        "entrada de mercancia", "codigo de barras", "referencia del producto",
        "producto nuevo", "actualizar precios", "tarifa", "lista de precios",
        "descuento en el pos", "vigencia de precios", "no aparece el articulo",
        "cargar productos", "importar productos", "existencia en bodega",
        "costo del producto", "precio de venta", "no me deja cambiar el precio",
        "margen del producto", "unidades en existencia", "producto agotado",
        "no guarda", "no actualiza", "no aparece", "no descuenta",
    ],
    "Puntos de venta::POS Lectores y Balanzas": [
        "lector", "lector de codigo", "scanner", "balanza", "pesaje", "pesa",
        "no lee el codigo", "no escanea", "codigo de barras", "huella del producto",
        "balanza no conectada", "peso", "ticket de la balanza", "etiqueta",
        "lector de infrared", "no lee las barras", "balanza del punto de venta",
        "falla la balanza", "no pesa", "no enciende", "no prende",
        "se daña", "se rompio", "pesaje incorrecto", "peso incorrecto",
        "no me lee el producto", "el lector no funciona", "balanza se apaga",
        "balanza marca mal", "no conecta la balanza", "codigo no lo lee",
        "no lee", "marca mal",
    ],
    "Puntos de venta::POS Sincronización y Datos": [
        "no sincroniza", "sincronizar", "sincronizacion", "se descuadraron los datos",
        "no sube la venta", "no llega la venta a siesa", "siesa no ve el pos",
        "importar datos", "exportar datos", "respaldo del pos", "base de datos del pos",
        "perdida de datos", "info desactualizada", "los datos del pos",
        "no llego la venta", "venta duplicada", "se duplico la venta",
        "no cuadra con siesa", "diferencia de inventario entre siesa y el pos",
        "no me deja sincronizar", "proceso de sincronizacion",
        "no llega", "no guarda",
    ],
    "Puntos de venta::Cajon Monedero": [
        "cajon", "monedero", "no abre el cajon", "cajon de monedas", "llave del cajon",
        "gaveta", "gaveta de dinero", "no abre la gaveta", "monedas", "billetes",
        "cajon portapiezas", "apertura de cajon", "cajon no responde", "efectivo",
        "no me abre el cajon", "el cajon queda abierto", "no cierro el cajon",
        "cajon de la caja", "monederero", "saco de monedas", "retiro de efectivo",
        "falta dinero en caja", "sobra dinero en caja",
        # Estas tres sueltas se quitaron: con "no abre el POS" o "no me abre
        # el sistema" terminaban aquí tickets que no son del cajón.
        "no abre el cajon", "no cierra el cajon", "el cajon no abre",
    ],
    "Puntos de venta::Impresoras": [
        "impresora", "no imprime", "impresion", "cabezal", "papel", "cola de impresion",
        "impresora compartida", "driver impresora", "impresora de tickets",
        "impresora fiscal", "impresora termica", "epson", "zebra", "star",
        "ticket sin salir", "sale cortado", "imprime en blanco", "sin tinta",
        "cambio de cinta", "cambio de papel", "impresora de cocina", "comanda",
        "impresora no conectada", "spooler", "trabajo en cola", "imprime dos veces",
        "impresora del punto de venta", "impresora de la caja", "no sale el tiquete",
        "no sale el ticket", "sale a medias", "papel atascado", "error de impresora",
        "tira de papel", "bobina", "la impresora no responde", "impresora apagada",
        "imprime borroso", "imprime la mitad", "no imprime el tiquete",
        "reportadora", "impresora de la tienda", "impresora del local",
        "de la tienda", "del local", "en la tienda", "la tienda",
        "impresora del punto de venta", "impresora de la tienda", "mostrador",
        "imprime mal", "sale en blanco",
    ],
    # ================= Soporte TI =================
    "Soporte TI::Hardware": [
        "equipo", "falla fisica", "repuesto", "garantia", "hardware", "componente",
        "equipo no prende", "carcasa", "bisagra", "teclado", "mouse",
        "cambio de bateria", "equipo lento", "se daña", "partes del equipo",
        "no arranca el equipo", "equipo se apaga", "revision del equipo",
        "se dano", "se danio", "se dania",
        "el teclado no funciona", "el mouse no funciona", "no hay teclado",
        "cambio de teclado", "cambio de mouse", "equipo hace ruido",
        "equipo se calienta", "la bateria no carga", "no tiene carga",
        "se daño el portatil", "equipo no prende", "cambio de portatil",
        "revision tecnica", "equipo dado de baja", "compra de equipo",
        "no enciende", "no prende", "se apaga", "no responde", "se daño",
    ],
    "Soporte TI::Software": [
        "instalacion", "aplicacion", "office", "windows", "programa", "actualizacion",
        "licencia de software", "instalar", "sistema",
        "no abre el programa", "programa no instalado", "no me deja instalar",
        "aplicativo", "licencia", "sin licencia", "se vencio la licencia",
        "error de windows", "windows no arranca", "sistema operativo",
        "no me deja entrar al sistema", "no me abre nada", "programa no corre",
        "antivirus", "bloquea el programa", "programa bloqueado",
    ],
    "Soporte TI::Instalación de Software": [
        "instalar", "instalacion", "instalame", "no tengo instalado", "aplicacion",
        "descargar programa", "programa no instalado", "software nuevo", "licencia",
        "activar licencia", "sin licencia", "no abre el programa", "reinstalar",
        "software de la empresa", "aplicativo", "autoinstalable",
        "necesito instalar", "no tengo el programa", "pasame el instalador",
        "como instalo", "instalador", "setup", "no se instala", "la instalacion falla",
        "aplicacion de la empresa", "software requerido", "requiere instalacion",
    ],
    "Soporte TI::Actualizaciones y Parches": [
        "actualizacion", "actualizar", "update", "parche", "windows update",
        "actualizar windows", "sistema desactualizado", "reinstalar sistema",
        "actualizacion pendiente", "no deja actualizar", "version antigua", "upgrade",
        "antivirus no actualiza", "requiere reinicio", "pendiente de reiniciar",
        "el equipo pide reinicio", "windows update falla", "no puedo actualizar",
        "definitions no actualiza", "firma digital vencida", "windows 7",
        "sistema sin soporte", "dejo de actualizar",
    ],
    "Soporte TI::Impresoras y Escáneres": [
        "impresora", "escaner", "impresora de la oficina", "multifuncional",
        "no imprime la factura", "impresora de red", "spooler", "cola de impresion",
        "impresora nueva", "configurar impresora", "toner", "cartucho", "scan",
        "digitalizar", "escaneo", "impresora se desconecta", "usb", "compartir impresora",
        "no imprime", "no imprime nada", "se traba la impresora", "impresora del despacho",
        "la impresora no imprime", "impresora de ventas", "impresora de la sede",
        "impresora de la recepcion", "impresora del deposito",
    ],
    "Soporte TI::Navegador y Aplicaciones Web": [
        "navegador", "chrome", "edge", "firefox", "safari", "no carga la pagina",
        "pagina en blanco", "sitio caido", "no me deja entrar a la pagina", "web",
        "aplicacion web", "portal web", "certificado del navegador", "cache",
        "la pagina no abre", "error de la pagina", "no puedo acceder a la web",
        "no me abre la pagina", "proceso de la pagina", "la pagina queda cargando",
        "no me deja entrar a la web", "boton de la pagina", "portal del empleado",
        "navegador no abre", "actualizar el navegador", "cookies",
        "la pagina cambio", "direccion web", "link de la pagina",
        "el navegador no abre", "la pagina no carga", "no entra a la pagina",
    ],
    "Soporte TI::Microsoft 365 / Office": [
        "office", "microsoft 365", "outlook", "teams", "onedrive", "sharepoint",
        "word", "excel", "powerpoint", "outlook no abre", "no recibo correos",
        "no puedo adjuntar archivo", "onedrive no sincroniza", "microsoft teams",
        "correo corporativo", "licencia de office", "activar office", "cuenta microsoft",
        "no abre word", "no abre excel", "no abre teams", "no puedo compartir archivo",
        "archivo no se sube", "calendario de outlook", "contactos de outlook",
        "onedrive lleno", "no me deja entrar a teams", "reunion de teams",
        "no me deja entrar", "no puedo abrir",
    ],
    "Soporte TI::Correo": [
        "correo", "outlook", "email", "buzon", "no recibo correo", "no puedo enviar correo",
        "spam", "contrasena de correo", "correo enviado", "correos enviados",
        "adjunto no se envia", "firma de correo", "regla de correo", "no puedo responder",
        "correo lleno", "buzon lleno", "no llego el correo", "correo se queda enviado",
        "no puedo ver el correo", "se roba el correo", "redirigir correo",
        "firma electronica", "correos de dogger",
        # "el corre" se busca como subcadena, asi que tambien aparece dentro de
        # "el correlativo". El exclusion de arriba (factura, cufe, dian) es lo
        # que manda ese caso a la categoria correcta.
        "el corre", "la corre", "no me deja escribir el correo", "responder todos",
        "no llega", "no envía", "no me deja entrar",
    ],
    "Soporte TI::Red": [
        "internet", "wifi", "cable de red", "conectividad", "impresora de red", "sin red",
        "se cae la red", "no tengo internet", "velocidad lenta", "se desconecta",
        "no me conecta el wifi", "clave de wifi", "red inalambrica", "punto de acceso",
        "no hay señal", "se desconecta el internet", "wifi no funciona",
        "conectarse a la red", "red lenta",
        "se cae", "sin internet", "no tiene señal",
    ],
    "Soporte TI::Otros problemas": [
        "no se que paso", "no se que paso", "ayuda", "no entiendo", "como hago",
        "no se", "no idea", "tengo una duda", "no se donde reportar",
        "otro problema", "problema raro", "no se me que es", "consulta",
        "no se a quien pedirle", "no ubico", "no encuentro como",
        "no funciona nada", "nada funciona", "no me funciona nada",
        "ayer funcionaba", "antes funcionaba", "no se por que",
    ],
    # ================= Endpoints =================
    "Endpoints::PC / Laptop": [
        "pc", "computador", "laptop", "portatil", "no enciende", "lento", "pantalla azul",
        "disco duro", "ram", "teclado", "mouse", "reinicia solo",
        "pantalla azul", "se apaga solo", "equipo muy lento", "virus",
        "no arranca windows", "formateo", "cambio de disco", "memoria",
        "el computador no prende", "la pantalla se ve azul",
        "no prende", "se apaga", "se daño",
    ],
    "Endpoints::Perifericos": [
        "periferico", "teclado", "mouse", "video beamer", "proyector", "parlante",
        "auricular", "webcam", "tablet", "manos libres", "cable de hdmi",
        "diagrama", "base para portatil", "mochila", "dongle",
        "no responde", "no da click", "no funciona el mouse",
    ],
    # ================= Infraestructura =================
    "Infraestructura::Red / Switch": [
        "red", "switch", "no hay red", "internet", "wifi", "cable", "conexion", "puerto",
        "vlan", "datos", "navegacion", "router", "caida de red",
        "no hay conectividad", "switch no responde", "puerto del switch",
        "se cae la red del local", "red del punto de venta",
        "se cae", "sin internet", "no tiene señal",
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
        "antivirus", "consola", "virus", "malware", "infeccion", "proteccion",
        "endpoint security",
    ],
    "Infraestructura::Sistema de Marcacion": [
        "marcacion", "biometrico", "huella", "reloj", "asistencia", "marcaje", "entrada y salida",
    ],
    # ================= Integraciones =================
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
    # ================= Administrativo TI =================
    "Administrativo TI::Creacion Usuario": [
        "crear usuario", "creacion de usuario", "nuevo usuario", "cuenta nueva",
        "alta de usuario", "usuario directorio", "crear cuenta", "crear un usuario",
        "usuario nuevo", "crear usuario nuevo", "no puedo crear usuario",
        "creacion del usuario", "crear el usuario de un empleado",
        "necesito un usuario", "alta de un nuevo colaborador",
    ],
    "Administrativo TI::Permisos": [
        "permisos", "permiso de acceso", "carpeta compartida", "acceso a carpeta",
        "permisos de red", "roles", "no tengo permisos",
    ],
    "Administrativo TI::Accesos": [
        "accesos", "acceso", "credenciales", "contrasena", "desbloquear", "bloqueado",
        "no me deja ingresar", "no me deja iniciar sesion", "usuario bloqueado",
        "acceso a sistemas", "clave bloqueada", "no acepta la clave", "restablecer clave",
        "cambiar mi clave", "cambiar la contrasena", "no recuerdo mi clave",
        "resetear clave", "mi clave no funciona", "se me bloqueo la cuenta",
        "no me deja entrar", "mi usuario no funciona",
    ],
    "Administrativo TI::Solicitud Equipo": [
        "solicitud de equipo", "equipo nuevo", "computador nuevo", "cambio de equipo",
        "laptop nueva", "dotacion", "compra de equipo", "nuevo computador",
    ],
}

# Palabras que descartan una categoría: el POS y el soporte de oficina se
# parecen (una impresora que no imprime sirve para los dos), así que "la
# impresora de la oficina no imprime" debe caer en soporte TI y no en POS.
PALABRAS_EXCLUYE = {
    "Puntos de venta::POS Hardware": ["oficina", "departamento", "portatil", "laptop", "mouse"],
    "Puntos de venta::POS Software": ["oficina", "departamento"],
    "Puntos de venta::Impresoras": [
        "oficina", "departamento", "multifuncional", "toner", "cartucho",
        "escaner", "digitalizar", "escanear",
        # Si nombra Siesa, POS o factura, el problema es del sistema de Siesa
        # y no de la impresora de la tienda.
        "siesa", "pos", "punto de venta", "factura", "cufe", "dian",
    ],
    "Puntos de venta::POS Lectores y Balanzas": ["oficina", "departamento"],
    # "no llega" y "no envia" son palabras de correo, pero también de la factura
    # electrónica: si el texto nombra Siesa, POS o factura, manda la de Siesa.
    "Soporte TI::Correo": ["siesa", "pos", "punto de venta", "factura", "cufe", "dian"],
    # "sistema" y "no guarda" son palabras ambiguousas: si el texto nombra el
    # Siesa, un POS o una base de datos, manda la categoría que sí los nombra.
    "Soporte TI::Software": ["siesa", "pos", "punto de venta", "sincroniza", "caja"],
    # Las impresoras de Soporte TI son las de áreas comunes (oficina, activos).
    # Si el texto nombra Siesa, POS o factura, manda la de Siesa.
    "Soporte TI::Impresoras y Escáneres": [
        "siesa", "pos", "punto de venta", "factura", "cufe", "dian", "caja", "pvfe",
    ],
    "SIESA ERP::Ventas y pedidos": ["pos", "punto de venta", "sincroniza", "no sincroniza"],
    # "no guarda" sirve para las dos: decide si se habla de precios o de la venta.
    "Puntos de venta::POS Inventario y Precios": ["sincroniza", "base de datos", "venta"],
    "Puntos de venta::POS Sincronización y Datos": [
        "inventario", "catalogo", "precio", "producto",
    ],
    # Aqui caen las dos puertas de Siesa: la del ERP y la del punto de venta
    # (POS-FE). Antes se ofrecian como dos categorias distintas y el usuario
    # no sabia cual elegir; ahora es una sola, con las palabras de las dos.
    "SIESA ERP::Facturación electrónica": [
        # El POS con "caja" es el de Siesa, no el cajón de monedas.
        "pos", "punto de venta", "pvfe", "pdv", "siesa del punto de venta",
        "sincroniza", "sincronizacion", "sincronizar", "inventario", "catalogo",
        "balanza", "lector", "precio", "precios",
        "impresora", "cabezal", "papel", "cola de impresion", "no imprime",
        "se apaga", "se reinicia", "se traba", "pantalla", "no prende", "no enciende",
        # Facturacion electronica (DIAN/CUFE) tiene su propia categoria.
        "dian", "cufe", "cue", "factura electronica", "facturacion electronica",
        "documento invalido", "documento rechazado", "factura rechazada", "qr",
        # Y los problemas de programa o de lentitud son de POS Software.
        "lenta", "lento", "lentitud", "tarda", "demora", "se queda pensando",
        "se cuelga", "se congela", "se cierra", "se bloquea", "error del pos",
        "error de pos", "pos no abre", "no abre el pos", "base de datos del pos",
    ],
    # "sistemas" es la palabra comodín del Siesa: si además se menciona un
    # módulo o un POS, manda la categoría específica.
    "SIESA ERP::Otros problemas de Siesa": [
        "pos", "punto de venta", "caja", "correo", "outlook", "nomina",
        "sincroniza", "sincronizacion", "impresora", "cajon", "balanza", "lector",
        "inventario", "catalogo", "precios", "factura", "facturar",
        "documento", "documento invalido", "cufe", "dian",
        "internet", "wifi", "red", "produccion", "contabilidad",
    ],
}

# Antes de puntuar se cambia el texto a minúsculas sin tildes. Los signos se
# convierten en espacio para que "cajón," y "cajón." sean la misma cosa y no
# peguen dos palabras.
_SIN_SIGNO = re.compile(r"[^\w\s]+", re.UNICODE)
_ESPACIOS = re.compile(r"\s+")


def _norm(texto):
    """Minúsculas, sin tildes y sin signos, con espacios colapsados."""
    plano = "".join(
        c for c in unicodedata.normalize("NFD", (texto or "").lower())
        if unicodedata.category(c) != "Mn"
    )
    return _ESPACIOS.sub(" ", _SIN_SIGNO.sub(" ", plano)).strip()


def _construir_indice(tabla):
    indice = {}
    for clave, palabras in tabla.items():
        grupo, _, nombre = clave.partition("::")
        indice[f"{_norm(grupo)}::{_norm(nombre)}"] = palabras
    return indice


INDICE = _construir_indice(PALABRAS_CLAVE)
EXCLUYE = _construir_indice(PALABRAS_EXCLUYE)

# Qué cubre cada categoría, en una línea, para que el usuario sepa qué elegir
# sin adivinar. Se muestra en el desplegable de categoría del reporte.
QUEB_CUBRE = {
    "SIESA ERP::Ventas y pedidos": "Pedidos, cotizaciones, clientes, precios y cuentas por cobrar",
    "SIESA ERP::Producción y bodega": "Producción, recetas, lotes, calidad, mermas y bodega",
    "SIESA ERP::Contabilidad y pagos": "Contabilidad, impuestos, retenciones, bancos y pagos",
    "SIESA ERP::Facturación electrónica": "Facturas electrónicas, CUFE, resoluciones, cajas, tickets e impresoras fiscales, tanto en Siesa ERP como en Siesa POS",
    "SIESA ERP::Reportes y tableros": "Reportes, indicadores y análisis de ventas",
    "SIESA ERP::Otros problemas de Siesa": "Problemas de Siesa cuando no sabes en qué módulo están",
    "SIESA Web::Nomina Web": "Liquidación, pagos y reportes de nómina en la web",
    "SIESA Web::Autogestion": "Autoservicio del colaborador: cédulas, vacaciones y certificados",
    "SIESA Web::SiesaAccess": "Ingreso, contraseñas y permisos de Siesa Access",
    "SIESA Cloud::SIESA CLOUD-ERP": "Acceso, rendimiento y disponibilidad de Siesa en la nube",
    "Puntos de venta::POS Hardware": "Equipo de caja: no prende, pantalla, teclado o tarjeta",
    "Puntos de venta::POS Software": "El programa del POS se congela, se cierra o da error",
    "Puntos de venta::Cajon Monedero": "El cajón de monedas no abre o queda abierto",
    "Puntos de venta::Impresoras": "Tickets que no salen, salen cortados o en blanco",
    "Puntos de venta::POS Inventario y Precios": "Catálogo, precios, existencias y ajustes de inventario",
    "Puntos de venta::POS Lectores y Balanzas": "Lector de códigos y balanzas que no leen o no pesan",
    "Puntos de venta::POS Sincronizacion y Datos": "Ventas que no llegan a Siesa y datos descuadrados",
    "Endpoints::PC / Laptop": "Equipos de escritorio y portátiles de los usuarios",
    "Endpoints::Perifericos": "Mouse, teclado, monitor, audiovisual y otros accesorios",
    "Infraestructura::Red / Switch": "Conexión, cableado, switches, VLAN y puertos de red",
    "Infraestructura::Firewall Fortinet": "Bloqueos, reglas, VPN y configuración del Fortinet",
    "Infraestructura::WatchGuard": "Bloqueos, proxy y políticas del firewall WatchGuard",
    "Infraestructura::Server Principal": "Servidor de aplicaciones: lentitud, caídas y servicios",
    "Infraestructura::Terminal Server": "Escritorio remoto, reconexiones y lentitud de sesión",
    "Infraestructura::Servidor de Archivos": "Carpetas compartidas, permisos y acceso a archivos",
    "Infraestructura::Servidor de Correos": "Correo corporativo: envío, recepción y Outlook",
    "Infraestructura::Backup": "Respaldos, copias de seguridad y restauración",
    "Infraestructura::Antivirus / Consola": "Amenazas, cuarentena, políticas y despliegue del antivirus",
    "Infraestructura::Sistema de Marcacion": "Marcación, torniquete, huella y asistencia",
    "Integraciones::GenericTransfer": "Transferencia de archivos y datos entre sistemas",
    "Integraciones::Web Service": "Servicios web y consumos de la API",
    "Integraciones::Correos HUGE": "Envío masivo de correo y correo no entregado",
    "Soporte TI::Hardware": "Computadores, celulares y equipos que fallan",
    "Soporte TI::Software": "Programas que fallan, se cierran o dan error",
    "Soporte TI::Correo": "Outlook y correo: no envía, no recibe o no sincroniza",
    "Soporte TI::Red": "Internet, WiFi y conexión a la red del trabajo",
    "Soporte TI::Instalacion de Software": "Instalación de programas y permisos de instalación",
    "Soporte TI::Actualizaciones y Parches": "Windows, parches, actualizaciones y reinicios",
    "Soporte TI::Impresoras y Escaneres": "Impresoras, escáneres y papel en áreas comunes",
    "Soporte TI::Navegador y Aplicaciones Web": "Chrome, Firefox, páginas y formularios web",
    "Soporte TI::Microsoft 365 / Office": "Outlook, Word, Excel, Teams y SharePoint",
    "Soporte TI::Otros problemas": "Problemas de TI sin una categoría clara",
    "Administrativo TI::Creacion Usuario": "Creación de cuentas, correos y accesos de entrada",
    "Administrativo TI::Permisos": "Permisos a carpetas, programas y sistemas",
    "Administrativo TI::Accesos": "Ingreso, contraseña, bloqueo y desbloqueo de cuentas",
    "Administrativo TI::Solicitud Equipo": "Solicitud de computador, celular, monitor o periféricos",
}

# Las descripciones también se buscan por grupo::nombre ya normalizados, para
# que un nombre guardado en la base con tildes o mayúsculas no las pierda.
CUBRE_INDICE = _construir_indice(QUEB_CUBRE)

# Lo mismo, pero para los grupos de la vista de categorías: ayuda a saber de
# entrada en qué bloque reportar, sin abrir las 47 una por una.
GRUPO_CUBRE = {
    "SIESA ERP": "El ERP de Siesa, por módulos: ventas, producción, contabilidad, facturación electrónica y reportes",
    "SIESA Web": "Aplicaciones web de Siesa: nómina, autogestión y accesos",
    "Siesa Cloud": "Siesa en la nube: accesos, rendimiento y disponibilidad",
    "Puntos de venta": "El punto de venta de la sede: equipo, programa, inventario, lectoras, impresión y sincronización de datos",
    "Endpoints": "Equipos del usuario: computadoras, portátiles y periféricos",
    "Infraestructura": "Red, servidores, respaldos, antivirus y control de acceso",
    "Integraciones": "Intercambio de datos entre sistemas: transferencias, servicios web y correo masivo",
    "Soporte TI": "Soporte general: hardware, software, correo, red, Office e impresión",
    "Administrativo TI": "Trámites de cuenta: alta de usuarios, permisos, accesos y solicitud de equipos",
}
GRUPO_INDICE = {_norm(g): d for g, d in GRUPO_CUBRE.items()}



def _buscar_claves(grupo, nombre):
    """
    Palabras clave de la categoría. Se indexan por grupo::nombre ya
    normalizados (sin tildes, sin mayúsculas) para que el nombre guardado en
    la base no tenga que coincidir al carácter con el del diccionario.
    """
    return INDICE.get(f"{_norm(grupo)}::{_norm(nombre)}", [])


# Distancia máxima (caracteres) que se acepta entre dos palabras de una misma
# frase: permite "usuario esta bloqueado" sin unir frases de temas distintos
# ("problema con ... siesa" ya no cuenta como una sola).
HUECO_FRASE = 9


def _frase(texto, frase):
    """
    True si las palabras de la frase aparecen en orden y cerca.

    Cada palabra admite terminaciones, así que "impresora de la oficina"
    encuentra "impresoras de la oficina" y "no imprime" encuentra "no imprimen".
    """
    pos = 0
    for palabra in frase.split(" "):
        m = re.search(r"\b" + re.escape(palabra) + r"\w*", texto[pos:])
        if not m:
            return False
        if pos and m.start() > HUECO_FRASE:
            return False
        pos += m.end()
    return True


def _puntaje_texto(texto, claves, nombre, grupo, excluir=()):
    """
    Puntaje de un texto contra una categoría.

    Las frases valen más que una palabra suelta porque describen el problema
    completo ("no abre el cajon"). Y la palabra suelta tolera plural y
    terminaciones: "impresora" también encuentra "impresoras" o "impresora2".
    """
    if not texto:
        return 0
    score = 0
    for clave in claves:
        k = _norm(clave)
        if not k:
            continue
        if " " in k:
            if _frase(texto, k):
                score += PESO_FRASE
            continue
        if re.search(r"\b" + re.escape(k) + r"\w*", texto):
            score += PESO_PALABRA
        elif k in texto:
            score += PESO_PALABRA_SUELTA
    n, g = _norm(nombre), _norm(grupo)
    if n and re.search(r"\b" + re.escape(n) + r"\w*", texto):
        score += PESO_NOMBRE
    if g and re.search(r"\b" + re.escape(g) + r"\w*", texto):
        score += PESO_GRUPO
    return score


def _penalizacion(texto, excluir):
    """
    Cuánto resta el contexto de otra categoría.

    Cada palabra de la lista que aparece en el texto resta PESO_EXCLUYE, y el
    total se limita a MAXIMO_EXCLUSIONES: mencionar dos módulos concretos
    ("pos" + "inventario") dice mucho más que mencionar "pos" una vez, pero un
    texto no puede dejar el puntaje en cero negativo sin límite.
    """
    total = 0
    for palabra in excluir:
        k = _norm(palabra)
        if k and re.search(r"\b" + re.escape(k) + r"\w*", texto):
            total += PESO_EXCLUYE
            if total >= PESO_EXCLUYE * MAXIMO_EXCLUSIONES:
                return PESO_EXCLUYE * MAXIMO_EXCLUSIONES
    return total


def _puntaje(titulo, descripcion, categoria):
    """
    Puntaje del título y la descripción juntos. El título pesa el doble: es
    la frase corta que resume el problema y por eso dice más que el detalle.
    """
    clave = f"{_norm(categoria.grupo)}::{_norm(categoria.nombre)}"
    claves = INDICE.get(clave, [])
    t = _norm(titulo)
    d = _norm(descripcion)
    completo = f"{t} {d}".strip()
    score = _puntaje_texto(completo, claves, categoria.nombre, categoria.grupo)
    if t:
        score += PESO_TITULO * _puntaje_texto(
            t, claves, categoria.nombre, categoria.grupo
        )
    # El contexto se mira sobre todo el texto, no campo por campo: que el
    # título diga "sistema" no puede tapar un "no sincroniza" de la descripción.
    return score - _penalizacion(completo, EXCLUYE.get(clave, []))


# Desempate: con el mismo puntaje gana la categoría más urgente (menos horas
# de ANS) y, si sigue la igualdad, la primera en orden alfabético. Así la
# sugerencia no cambia de un momento a otro por el orden de la base.
_ORDEN_URGENCIA = {"urgente": 0, "alta": 1, "media": 2, "baja": 3}


def _es_comodin(categoria):
    """Las categorías "Otros ..." son el último recurso."""
    return _norm(categoria.nombre).startswith("otros ")


def _clave_desempate(categoria):
    return (
        # El comodín solo gana si puntúa más alto, nunca por empate.
        1 if _es_comodin(categoria) else 0,
        _ORDEN_URGENCIA.get(categoria.prioridad_default, 9),
        categoria.ans_horas or 9999,
        categoria.nombre,
    )


# Con 3 puntos ya se propone algo; a partir de UMBRAL_AUTO se aplica sola.
# Con el vocabulario amplio casi cualquier descripción real pasa de UMBRAL_AUTO.
UMBRAL_MINIMO = 3
UMBRAL_AUTO = 6
# Texto demasiado corto para elegir: mejor no proponer que proponer al azar.
MIN_CARACTERES = 8


def sugerir_categoria(titulo="", descripcion="", excluir=None):
    """
    Devuelve la Categoría más probable según el texto, o None si no hay
    una coincidencia clara (puntaje >= UMBRAL_MINIMO).
    """
    texto = _norm(f"{titulo} {descripcion}")
    if len(texto.strip()) < MIN_CARACTERES:
        return None
    mejor = None
    mejor_puntaje = 0
    qs = Categoria.objects.filter(activo=True)
    if excluir:
        qs = qs.exclude(pk=excluir)
    for cat in qs:
        p = _puntaje(titulo, descripcion, cat)
        if p > mejor_puntaje or (
            p == mejor_puntaje and mejor is not None and p > 0 and _clave_desempate(cat) < _clave_desempate(mejor)
        ):
            mejor = cat
            mejor_puntaje = p
    return mejor if mejor_puntaje >= UMBRAL_MINIMO else None


def que_cubre(grupo, nombre):
    """Línea de "qué cubre" de la categoría, para el desplegable del reporte."""
    return CUBRE_INDICE.get(f"{_norm(grupo)}::{_norm(nombre)}", "")


def que_cubre_grupo(grupo):
    """Línea de "qué cubre" de un grupo, para la vista de categorías."""
    return GRUPO_INDICE.get(_norm(grupo), "")


def claves_para_json():
    """
    Lista serializable para el sugeridor en el cliente.

    Se manda también la prioridad y el ANS de cada categoría para que el
    cliente pueda aplicar el mismo desempate que el servidor, y los pesos
    para que el JavaScript no los lleve escritos dentro. Cada categoría
    incluye su línea de "qué cubre" para el submenú del desplegable.
    """
    datos = []
    for cat in Categoria.objects.filter(activo=True).order_by("grupo", "nombre"):
        datos.append({
            "id": cat.pk,
            "grupo": cat.grupo,
            "nombre": cat.nombre,
            "cubre": que_cubre(cat.grupo, cat.nombre),
            "prioridad": cat.prioridad_default,
            "ans": cat.ans_horas,
            "claves": _buscar_claves(cat.grupo, cat.nombre),
            "excluye": EXCLUYE.get(f"{_norm(cat.grupo)}::{_norm(cat.nombre)}", []),
        })
    datos.append({
        "pesos": {
            "frase": PESO_FRASE,
            "palabra": PESO_PALABRA,
            "suelta": PESO_PALABRA_SUELTA,
            "nombre": PESO_NOMBRE,
            "grupo": PESO_GRUPO,
            "titulo": PESO_TITULO,
            "excluye": PESO_EXCLUYE,
        },
        "umbral": UMBRAL_MINIMO,
        "auto": UMBRAL_AUTO,
        "min_caracteres": MIN_CARACTERES,
        "hueco_frase": HUECO_FRASE,
        "maximo_exclusiones": MAXIMO_EXCLUSIONES,
    })
    return datos
