"""
Sugerencia automática de categoría: POS, soporte TI y prioridad del título.

La misma tabla de palabras la usan el servidor (forms.py) y el navegador
(static/js/dogger.js), así que aquí se fija el comportamiento que ambos deben
respetar: qué categoría gana, cuándo no se sugiere nada y cómo se desempata.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from apps.tickets.management.commands.seed_categorias import CATEGORIAS
from apps.tickets.models import Categoria
from apps.tickets.sla import horas_por_prioridad
from apps.tickets.sugerencia_categoria import (
    INDICE,
    MIN_CARACTERES,
    PALABRAS_CLAVE,
    CUBRE_INDICE,
    QUEB_CUBRE,
    UMBRAL_AUTO,
    UMBRAL_MINIMO,
    _norm,
    claves_para_json,
    sugerir_categoria,
)


class CatalogoDePrueba(TestCase):
    """Crea el catálogo real del seed: los tests corren contra la base de test."""

    @classmethod
    def setUpTestData(cls):
        for grupo, nombre, prioridad in CATEGORIAS:
            Categoria.objects.create(
                grupo=grupo,
                nombre=nombre,
                activo=True,
                prioridad_default=prioridad,
                ans_horas=horas_por_prioridad(prioridad),
            )

    def nombre_de(self, categoria):
        return f"{categoria.grupo}::{categoria.nombre}"


class SugerenciaPuntosDeVenta(CatalogoDePrueba):
    def test_cajon_que_no_abre(self):
        c = sugerir_categoria(
            "El cajón de monedas no abre",
            "Cada vez que cobro tengo que abrirlo a mano",
        )
        self.assertEqual(self.nombre_de(c), "Puntos de venta::Cajon Monedero")

    def test_impresora_del_pos(self):
        c = sugerir_categoria(
            "La impresora del punto de venta no imprime los tickets",
            "Sale el papel pero queda la hoja sin texto",
        )
        self.assertEqual(self.nombre_de(c), "Puntos de venta::Impresoras")

    def test_pos_hardware(self):
        c = sugerir_categoria(
            "No prende el PC del punto de venta",
            "La pantalla se queda en negro, no enciende el equipo",
        )
        self.assertEqual(self.nombre_de(c), "Puntos de venta::POS Hardware")

    def test_pos_software_se_traba(self):
        c = sugerir_categoria(
            "El POS se traba y se cierra solo",
            "Muestra un error del programa al cobrar",
        )
        self.assertEqual(self.nombre_de(c), "Puntos de venta::POS Software")

    def test_facturacion_electronica(self):
        c = sugerir_categoria(
            "La factura electrónica sale rechazada",
            "No me deja facturar, dice documento no válido",
        )
        self.assertEqual(
            self.nombre_de(c), "SIESA ERP::Facturación electrónica"
        )

    def test_la_facturacion_electronica_tambien_cubre_el_pos(self):
        """Una sola categoría: lo que pasa en el POS de Siesa cae aquí."""
        casos = [
            ("No me llega el CUFE de la factura",
             "La factura electrónica no se autoriza en la DIAN"),
            ("En el POS de la caja 5 no imprime la factura",
             "No sale el tiquete de la venta"),
            ("El correlativo de la factura no sube",
             "No me deja emitir la venta"),
        ]
        for titulo, detalle in casos:
            with self.subTest(titulo=titulo):
                self.assertEqual(
                    self.nombre_de(sugerir_categoria(titulo, detalle)),
                    "SIESA ERP::Facturación electrónica",
                )

    def test_el_reporte_no_va_al_cajon(self):
        """"No me abre" a secas se llevaba el cajón; el reporte manda."""
        c = sugerir_categoria(
            "No me abre el reporte de ventas",
            "El tablero no carga y no veo los indicadores",
        )
        self.assertEqual(self.nombre_de(c), "SIESA ERP::Reportes y tableros")

    def test_una_impresora_de_oficina_no_es_la_del_pos(self):
        c = sugerir_categoria(
            "La impresora de la oficina no imprime",
            "No saca copias de los documentos",
        )
        self.assertEqual(self.nombre_de(c), "Soporte TI::Impresoras y Escaneres")

    def test_inventario_y_precios(self):
        c = sugerir_categoria(
            "No carga el catálogo en el POS",
            "Los productos no aparecen y no puedo cobrar bien",
        )
        self.assertEqual(self.nombre_de(c), "Puntos de venta::POS Inventario y Precios")

    def test_lector_y_balanza(self):
        c = sugerir_categoria(
            "El lector de códigos no lee los productos",
            "El scanner no escanea, hay que digitarlos a mano",
        )
        self.assertEqual(self.nombre_de(c), "Puntos de venta::POS Lectores y Balanzas")

    def test_sincronizacion_con_siesa(self):
        c = sugerir_categoria(
            "El POS no sincroniza con SIESA",
            "Las ventas del punto de venta no llegan a SIESA, el inventario quedó descuadrado",
        )
        self.assertEqual(self.nombre_de(c), "Puntos de venta::POS Sincronizacion y Datos")


class SugerenciaSoporteTI(CatalogoDePrueba):
    def test_correo(self):
        c = sugerir_categoria(
            "No recibo correos en el buzón",
            "El correo no llega y me devuelve los enviados",
        )
        self.assertEqual(self.nombre_de(c), "Soporte TI::Correo")

    def test_instalacion_de_software(self):
        c = sugerir_categoria(
            "Instalar programa nuevo, no tengo instalado el software",
            "Necesito el aplicativo que usan en tesorería",
        )
        self.assertEqual(self.nombre_de(c), "Soporte TI::Instalacion de Software")

    def test_actualizaciones_y_parches(self):
        c = sugerir_categoria(
            "El sistema está desactualizado, hay un parche pendiente",
            "Pide reinicio para actualizar Windows",
        )
        self.assertEqual(self.nombre_de(c), "Soporte TI::Actualizaciones y Parches")

    def test_navegador_y_aplicaciones_web(self):
        c = sugerir_categoria(
            "No puedo acceder a la página web",
            "Chrome no carga la página del portal",
        )
        self.assertEqual(self.nombre_de(c), "Soporte TI::Navegador y Aplicaciones Web")

    def test_microsoft_365(self):
        c = sugerir_categoria(
            "Outlook no abre y no puedo adjuntar archivo",
            "Office no responde, el correo no me deja enviar",
        )
        self.assertEqual(self.nombre_de(c), "Soporte TI::Microsoft 365 / Office")

    def test_impresora_de_oficina_no_es_la_del_pos(self):
        """El contexto manda: "de la oficina" saca el ticket del grupo POS."""
        c = sugerir_categoria(
            "Las impresoras de la oficina no imprimen",
            "La multifuncional del departamento queda en cola",
        )
        self.assertEqual(self.nombre_de(c), "Soporte TI::Impresoras y Escaneres")

    def test_portatil_de_oficina_no_es_hardware_de_pos(self):
        c = sugerir_categoria(
            "El portátil de la oficina no enciende",
            "Le tocó revisión, no prende el equipo",
        )
        self.assertEqual(self.nombre_de(c), "Endpoints::PC / Laptop")


class SugerenciaCriterio(CatalogoDePrueba):
    def test_texto_corto_no_sugiere(self):
        self.assertIsNone(sugerir_categoria("hola", "no"))
        self.assertIsNone(sugerir_categoria("", ""))

    def test_sin_coincidencia_cae_en_el_comodin(self):
        """Sin un módulo claro lo correcto es el comodín, no adivinar."""
        c = sugerir_categoria("Consulta sobre el contrato", "Solo quiero información")
        self.assertIsNotNone(c)
        self.assertEqual(self.nombre_de(c), "Soporte TI::Otros problemas")

    def test_una_sola_palabra_no_alcanza(self):
        self.assertIsNone(sugerir_categoria("raton", "si"))

    def test_categoria_inactiva_no_sugiere(self):
        """Desactivar una categoría la saca del catálogo, no la borra."""
        Categoria.objects.filter(grupo="Puntos de venta", nombre="Impresoras").update(
            activo=False
        )
        c = sugerir_categoria(
            "Las impresoras de la oficina no imprimen",
            "La multifuncional del departamento queda en cola",
        )
        self.assertEqual(self.nombre_de(c), "Soporte TI::Impresoras y Escaneres")
        # ...y sigue existiendo para el histórico, solo que no se propone.
        self.assertTrue(
            Categoria.objects.filter(
                grupo="Puntos de venta", nombre="Impresoras", activo=False
            ).exists()
        )

    def test_la_descripcion_refina_el_titulo(self):
        """Escribir más corrige la categoría: no queda clavada con el título."""
        con_titulo = sugerir_categoria("No imprime", "")
        con_detalle = sugerir_categoria(
            "No imprime", "Es la impresora de la oficina, la multifuncional"
        )
        self.assertEqual(self.nombre_de(con_titulo), "Puntos de venta::Impresoras")
        self.assertEqual(
            self.nombre_de(con_detalle), "Soporte TI::Impresoras y Escaneres"
        )

    def test_tildes_y_signos_no_importan(self):
        con_tilde = sugerir_categoria("El cajón, no abre.", "")
        sin_tilde = sugerir_categoria("El cajon no abre", "")
        self.assertEqual(self.nombre_de(con_tilde), "Puntos de venta::Cajon Monedero")
        self.assertEqual(self.nombre_de(sin_tilde), "Puntos de venta::Cajon Monedero")

    def test_plurales_y_terminaciones(self):
        c = sugerir_categoria("Las impresoras no imprimen los recibos", "")
        self.assertIsNotNone(c)
        c2 = sugerir_categoria("Los lectores no leen nada", "")
        self.assertIsNotNone(c2)

    def test_desempate_por_urgencia(self):
        """A igual puntaje gana la más urgente, no la que aparece primero."""
        from apps.tickets.sugerencia_categoria import _puntaje

        # Dos categorías de prueba con el mismo vocabulario y el mismo ANS:
        # solo cambia la prioridad, así que el desempate queda forzado.
        for nombre, prioridad in [("Zeta Urgente", "urgente"), ("Alfa Leve", "baja")]:
            Categoria.objects.create(
                grupo="Prueba",
                nombre=nombre,
                activo=True,
                prioridad_default=prioridad,
                ans_horas=24,
            )
            INDICE[f"prueba::{_norm(nombre)}"] = ["palabra de prueba"]

        urgente = Categoria.objects.get(nombre="Zeta Urgente")
        leve = Categoria.objects.get(nombre="Alfa Leve")
        titulo = "Falla la palabra de prueba"
        self.assertEqual(_puntaje(titulo, "", urgente), _puntaje(titulo, "", leve))
        self.assertEqual(sugerir_categoria(titulo, "").nombre, "Zeta Urgente")

    def test_desempate_es_estable_entre_lecturas(self):
        """La misma descripción da siempre la misma categoría."""
        titulo = "El POS se traba y se cierra solo"
        desc = "Muestra un error del programa al cobrar"
        primero = sugerir_categoria(titulo, desc)
        for _ in range(5):
            otro = sugerir_categoria(titulo, desc)
            self.assertEqual(self.nombre_de(otro), self.nombre_de(primero))

    def test_umbral_minimo(self):
        self.assertEqual(UMBRAL_MINIMO, 3)
        self.assertEqual(MIN_CARACTERES, 8)


class SugerenciaTextoPegado(CatalogoDePrueba):
    """Lo que pasa al pegar el reporte completo: debe quedar categoría siempre."""

    def test_punto_de_venta_completo(self):
        casos = [
            ("La factura no imprime los tickets",
             "En el punto de venta de Envigado la impresora fiscal no saca el tiquete.",
             "SIESA ERP::Facturación electrónica"),
            ("no me funciona el sistema",
             "cuando abro el siesa me sale un error y no me deja hacer nada",
             "SIESA ERP::Otros problemas de Siesa"),
            ("problema con los sistemas",
             "siesa pos no sincroniza con la base, me dice que la venta no se guardo",
             "Puntos de venta::POS Sincronizacion y Datos"),
            ("error en el siesa pos",
             "no puedo facturar, sale documento invalido",
             "SIESA ERP::Facturación electrónica"),
            ("el corre se borro",
             "no se que paso pero no me deja abrir nada",
             "Soporte TI::Correo"),
            ("se daño el mouse", "no responde el boton, ya no da click", "Soporte TI::Hardware"),
            ("quiero cambiar mi clave",
             "no me la puedo cambiar porque no me deja iniciar sesion",
             "Administrativo TI::Accesos"),
            ("la maquina del punto de venta esta lenta",
             "tarda mucho en cobrar y a veces se queda pensando",
             "Puntos de venta::POS Software"),
            ("impresora", "la impresora de la tienda no imprime nada",
             "Puntos de venta::Impresoras"),
            ("ayuda", "no se", "Soporte TI::Otros problemas"),
            ("cual es el problema", "ayer trabajamos bien y hoy nada funciona",
             "Soporte TI::Otros problemas"),
            ("sistemas", "siesa", "SIESA ERP::Otros problemas de Siesa"),
        ]
        for titulo, descripcion, esperado in casos:
            c = sugerir_categoria(titulo, descripcion)
            self.assertIsNotNone(c, f"sin sugerencia para {titulo!r}")
            self.assertEqual(self.nombre_de(c), esperado, f"titulo={titulo!r}")

    def test_umbral_de_auto_es_mas_bajo_que_el_de_sugerencia(self):
        """Todo lo que llega a sugerirse tiene que llegar a aplicarse."""
        self.assertLess(UMBRAL_MINIMO, UMBRAL_AUTO)
        self.assertLessEqual(UMBRAL_AUTO, UMBRAL_MINIMO + 3)

    def test_texto_muy_corto_no_propone_nada(self):
        self.assertIsNone(sugerir_categoria("s", "x"))
        self.assertIsNone(sugerir_categoria("sistema", ""))

    def test_comodin_no_se_come_los_casos_especificos(self):
        """El comodin del Siesa cede cuando el texto nombra un modulo."""
        c = sugerir_categoria(
            "problema con los sistemas", "siesa pos no sincroniza con la base"
        )
        self.assertNotEqual(self.nombre_de(c), "SIESA ERP::Otros problemas de Siesa")


class JsCategoriaEstatica(SimpleTestCase):
    """
    El bloque de categoría de dogger.js ya Slateó una vez por llamar
    pintarAuto() cuando la función se llamaba PintarAuto(): el navegador solo
    lo deja en la consola y el usuario ve que no le autocompleta nada. Estos
    tests fallan si se repite ese tipo de error.
    """

    RUTA = Path(__file__).resolve().parents[2] / "static" / "js" / "dogger.js"

    def _bloque(self):
        js = self.RUTA.read_text(encoding="utf-8")
        # el rótulo está dentro del comentario de cabecera: se corta desde su
        # cierre para que el bloque sea solo código
        inicio = js.index("*/", js.index("Categoría inteligente")) + 2
        fin = js.index("Resaltado ANS")
        bloque = js[inicio:fin]
        # y fuera los comentarios que quedan: un "mover la categoría(" dentro de
        # un // no es una llamada, es texto que puede decir cualquier cosa
        return re.sub(r"/\*.*?\*/|//[^\n]*", "", bloque, flags=re.S)

    def test_no_llama_a_funciones_que_no_existen(self):
        bloque = self._bloque()
        definidas = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", bloque))
        llamadas = set(re.findall(r"(?<![.\w$])([a-zA-Z_$][\w$]*)\s*\(", bloque))
        externas = {
            "if", "for", "while", "switch", "catch", "return", "typeof", "function",
            "new", "Math", "JSON", "String", "Number", "Array", "Object", "Boolean",
            "RegExp", "Event", "setTimeout", "clearTimeout", "parseInt", "parseFloat",
            "isNaN", "require", "fetch", "var", "do", "else", "try",
        }
        self.assertEqual(llamadas - definidas - externas, set())

    def test_escucha_pegar_y_arrastrar(self):
        """Si solo escuchara 'input', un pegado desde otra app podria quedar
        fuera y el usuario veria que no le autocompleta."""
        bloque = self._bloque()
        for evento in ("input", "change", "paste", "drop"):
            self.assertIn(f'"{evento}"', bloque, f"falta escuchar {evento}")

    def _llaves_desbalanceadas(self, js):
        """Lista de (linea, tipo) donde el archivo cierra mas de lo que abre.

        Recorre el codigo saltando comentarios, cadenas y regex, porque una
        llave dentro de un texto no cuenta.
        """
        pila, salida, modo, previo = [], [], "normal", ""
        abre = {"(": ")", "[": "]", "{": "}"}
        cierra = {v: k for k, v in abre.items()}
        for numero, linea in enumerate(js.split("\n"), 1):
            i = 0
            while i < len(linea):
                c = linea[i]
                if modo in ("comentario", "simple", "doble", "plantilla", "regex"):
                    if c == "\\":
                        i += 2
                        continue
                    if modo == "comentario" and c == "*" and linea[i + 1:i + 2] == "/":
                        modo = "normal"; i += 2; continue
                    if modo == "simple" and c == "'": modo = "normal"
                    if modo == "doble" and c == '"': modo = "normal"
                    if modo == "plantilla" and c == "`": modo = "normal"
                    if modo == "regex" and c == "/": modo = "normal"
                    i += 1
                    continue
                if c == "/" and linea[i + 1:i + 2] == "/":
                    break
                if c == "/" and linea[i + 1:i + 2] == "*":
                    modo = "comentario"; i += 2; continue
                if c == "'": modo = "simple"
                elif c == '"': modo = "doble"
                elif c == "`": modo = "plantilla"
                elif c == "/":
                    if previo in "(,=:[!&|?{};+-*%~^<>" or previo == "":
                        modo = "regex"
                elif c in abre:
                    pila.append((c, numero))
                elif c in cierra:
                    if not pila or pila[-1][0] != cierra[c]:
                        salida.append((numero, "cierra sin abrir"))
                        if pila: pila.pop()
                    else:
                        pila.pop()
                previo = c
                i += 1
        salida.extend((n, "nunca se cierra") for _, n in pila)
        return salida

    def test_umbrales_vienen_del_servidor(self):
        bloque = self._bloque()
        self.assertIn("item.umbral", bloque)
        self.assertIn("item.auto", bloque)

    def test_el_js_completo_parsea(self):
        """Una llave de mas en dogger.js y el navegador deja de ejecutar TODO el
        archivo: no autocompleta la categoria, los toasts no se cierran y la
        emergente de avisos no se puede cerrar. Sin avisar, es muy dificil
        ver que paso, asi que aqui se comprueba el archivo entero."""
        js = self.RUTA.read_text(encoding="utf-8")
        try:
            import esprima
        except ImportError:
            self.assertEqual(self._llaves_desbalanceadas(js), [])
        else:
            # esprima se queda en ES2017: el ?. de ES2020 se le Sustrae
            esprima.parseScript(re.sub(r"\?\.", ".", js))


class DatosParaElNavegador(CatalogoDePrueba):
    def test_lleva_pesos_umbrales_y_categorias(self):
        datos = claves_para_json()
        meta = datos[-1]
        for clave in ("frase", "palabra", "nombre", "titulo", "excluye"):
            self.assertIn(clave, meta["pesos"])
        self.assertEqual(meta["umbral"], UMBRAL_MINIMO)

        categoria = next(c for c in datos if c["nombre"] == "Cajon Monedero")
        self.assertEqual(categoria["grupo"], "Puntos de venta")
        self.assertIn("prioridad", categoria)
        self.assertIn("ans", categoria)
        self.assertTrue(categoria["claves"])
        self.assertIsInstance(categoria["excluye"], list)

    def test_toda_categoria_nueva_tiene_palabras(self):
        """Si una categoría se queda sin vocabulario nunca se autodetecta."""
        nuevas = [
            ("SIESA ERP", "Facturación electrónica"),
            ("Puntos de venta", "POS Inventario y Precios"),
            ("Puntos de venta", "POS Lectores y Balanzas"),
            ("Puntos de venta", "POS Sincronizacion y Datos"),
            ("Soporte TI", "Instalacion de Software"),
            ("Soporte TI", "Actualizaciones y Parches"),
            ("Soporte TI", "Impresoras y Escaneres"),
            ("Soporte TI", "Navegador y Aplicaciones Web"),
            ("Soporte TI", "Microsoft 365 / Office"),
            ("Soporte TI", "Otros problemas"),
            ("SIESA ERP", "Otros problemas de Siesa"),
            ("SIESA ERP", "Ventas y pedidos"),
            ("SIESA ERP", "Producción y bodega"),
            ("SIESA ERP", "Contabilidad y pagos"),
            ("SIESA ERP", "Facturación electrónica"),
            ("SIESA ERP", "Reportes y tableros"),
        ]
        for grupo, nombre in nuevas:
            clave = f"{_norm(grupo)}::{_norm(nombre)}"
            self.assertTrue(INDICE.get(clave), f"{clave} sin palabras clave")

    def test_indice_tolera_tildes(self):
        """La clave se busca sin tildes: el nombre en la base puede diferir."""
        clave_crudo = "SIESA ERP::Facturación electrónica"
        clave = f"{_norm('SIESA ERP')}::{_norm('Facturación electrónica')}"
        self.assertIn(clave_crudo, PALABRAS_CLAVE)
        self.assertIn(clave, INDICE)


class QueCubreCadaCategoria(SimpleTestCase):
    """
    El submenú del desplegable de categoría muestra la línea de "qué cubre" de
    cada categoría. Si falta una, el usuario ve un espacio en blanco y no sabe
    qué está eligiendo, así que aquí se revisa el catálogo completo.
    """

    def test_toda_categoria_del_catalogo_tiene_descripcion(self):
        faltantes = [
            f"{grupo} :: {nombre}" for grupo, nombre, _ in CATEGORIAS
            if not CUBRE_INDICE.get(f"{_norm(grupo)}::{_norm(nombre)}")
        ]
        self.assertEqual(faltantes, [], "categorías sin línea de 'qué cubre'")

    def test_las_descripciones_no_se_repiten(self):
        self.assertEqual([d for d in QUEB_CUBRE.values() if not d.strip()], [])
        self.assertEqual(
            len(set(QUEB_CUBRE.values())), len(QUEB_CUBRE),
            "hay dos categorías con la misma descripción",
        )

    def test_el_submenu_va_dentro_del_apartado_categoria(self):
        """Se inyecta dentro del bloque del campo, justo debajo del <select>:
        fuera de ese div el control queda suelto en la rejilla del formulario."""
        campo = Path(__file__).resolve().parents[2] / "templates" / "tickets" / "_form_field.html"
        texto = campo.read_text(encoding="utf-8")
        self.assertLess(texto.index("{{ field }}"), texto.index("_cat_que_cubre.html"))
        self.assertLess(texto.index("_cat_que_cubre.html"), texto.index("field-help"))

    def test_el_submenu_trae_sus_ganchos(self):
        partial = Path(__file__).resolve().parents[2] / "templates" / "tickets" / "_cat_que_cubre.html"
        texto = partial.read_text(encoding="utf-8")
        for marca in ('id="cat-cubre"', 'id="cat-cubre-toggle"', 'id="cat-cubre-lista"'):
            self.assertIn(marca, texto)

    def test_el_submenu_no_pinta_comentarios(self):
        """El {# ... #} de Django solo vale en una línea. Si el comentario salta
        de línea, el motor lo trata como texto y aparece pintado en la página."""
        partial = Path(__file__).resolve().parents[2] / "templates" / "tickets" / "_cat_que_cubre.html"
        self.assertNotIn("{#", partial.read_text(encoding="utf-8"))


class SubcategoriasSiesaEntendiblesTest(TestCase):
    """La migración 0015 deja los módulos de Siesa con nombre de usuario."""

    def test_la_migracion_renombra_las_subcategorias_viejas(self):
        from apps.tickets.models import Categoria as Cat

        Cat.objects.create(grupo="SIESA ERP", nombre="Biable")
        Cat.objects.create(grupo="SIESA ERP", nombre="POS-FE")
        Cat.objects.create(grupo="SIESA ERP", nombre="Otros sistemas")

        import importlib.util

        from django.apps import apps as django_apps
        from pathlib import Path

        ruta = (
            Path(__file__).parent
            / "migrations"
            / "0015_subcategorias_siesa_entendibles.py"
        )
        spec = importlib.util.spec_from_file_location("mig_0015", ruta)
        migracion = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migracion)
        migracion.renombrar(django_apps, None)

        nombres = set(Cat.objects.filter(grupo="SIESA ERP").values_list("nombre", flat=True))
        self.assertEqual(
            nombres, {"Reportes y tableros", "Facturación electrónica", "Otros problemas de Siesa"}
        )

    def test_la_0016_deja_una_sola_categoria_de_facturacion_electronica(self):
        """Facturación electrónica se ofrece una vez, en SIESA ERP, y sirve
        tanto para el ERP como para el POS."""
        import importlib.util
        from importlib import import_module
        from pathlib import Path

        from django.apps import apps as django_apps

        from apps.tickets.models import Categoria as Cat

        siesa = Cat.objects.create(grupo="SIESA ERP", nombre="POS-FE")
        pos = Cat.objects.create(grupo="Puntos de venta", nombre="POS Facturacion Electronica")
        pos.glpi_category_id = 77
        pos.save()

        ruta = Path(__file__).parent / "migrations" / "0016_facturacion_electronica_unificada.py"
        spec = importlib.util.spec_from_file_location("mig_0016", ruta)
        migracion = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migracion)
        migracion.unificar(django_apps, None)

        siesa.refresh_from_db()
        pos.refresh_from_db()
        self.assertEqual(siesa.nombre, "Facturación electrónica")
        self.assertEqual(siesa.glpi_category_id, 77)   # el ID de GLPI no se pierde
        self.assertFalse(pos.activo)                   # la de Puntos de venta sale del catálogo

        activas = Cat.objects.filter(activo=True, nombre__iexact="Facturación electrónica")
        self.assertEqual([c.grupo for c in activas], ["SIESA ERP"])

    def test_los_nombres_nuevos_siguen_con_descripcion_y_palabras(self):
        for nombre in ("Ventas y pedidos", "Producción y bodega", "Contabilidad y pagos",
                       "Facturación electrónica", "Reportes y tableros",
                       "Otros problemas de Siesa"):
            clave = f"{_norm('SIESA ERP')}::{_norm(nombre)}"
            self.assertTrue(INDICE.get(clave), f"{clave} sin palabras clave")
            self.assertTrue(CUBRE_INDICE.get(clave), f"{clave} sin descripcion")
